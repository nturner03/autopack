package io.github.pexp.devtools.client;

import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.brigadier.Command;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import io.github.pexp.devtools.PexpDevtools;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Pattern;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.client.event.RegisterClientCommandsEvent;
import net.neoforged.neoforge.client.event.RenderFrameEvent;
import net.neoforged.neoforge.common.NeoForge;

/**
 * Client half of pexp_devtools: the {@code /studio} capture commands (lite
 * scope: ping, clean, shot, panorama). Loaded on the client dist only, so the
 * dedicated server never sees a client class.
 *
 * <p>Every command answers with one system chat line starting {@code studio: }
 * (sent through the chat listener, so MCPFabric's {@code get_recent_chat} and
 * the client log see it). Files go to {@code <gamedir>/studio/}; reply paths
 * are relative to the game directory.
 *
 * <p>Captures are read from real frames: the command sets up the state, the
 * game renders normal frames, and {@link RenderFrameEvent.Post} (after the
 * frame is drawn, before it is shown) reads the main render target. Calling
 * {@code GameRenderer.renderLevel} outside the frame loop, as vanilla's
 * {@code Minecraft.grabPanoramixScreenshot} does, gave broken images in the
 * headless client (2026-10-31): sky but no terrain in a separate render
 * target, terrain but a black sky in the main one.
 */
@Mod(value = PexpDevtools.MOD_ID, dist = Dist.CLIENT)
public final class StudioClient {
    static final String DIR = "studio";
    static final Pattern NAME = Pattern.compile("[a-z0-9_-]{1,64}");
    static final int PANORAMA_MAX = 2048;
    /** Frames rendered with the new state before a capture reads one. */
    private static final int SETTLE_FRAMES = 3;
    /** Longest a panorama face waits for its chunk sections to compile. */
    private static final long FACE_SETTLE_MS = 5000;

    private final String version;
    private boolean clean;

    // At most one capture at a time. Commands and frame events run on the
    // client main (render) thread, so no locking is needed.
    private String shotName;
    private int shotFrames;
    private boolean shotPrevHideGui;
    private long shotQueuedAt;
    private Panorama panorama;

    public StudioClient(IEventBus modBus, ModContainer container) {
        this.version = container.getModInfo().getVersion().toString();
        NeoForge.EVENT_BUS.addListener(this::registerCommands);
        NeoForge.EVENT_BUS.addListener(this::onFramePre);
        NeoForge.EVENT_BUS.addListener(this::onFramePost);
    }

    private void registerCommands(RegisterClientCommandsEvent event) {
        event.getDispatcher().register(Commands.literal("studio")
                .then(Commands.literal("ping").executes(ctx -> ping()))
                .then(Commands.literal("clean")
                        .then(Commands.literal("on").executes(ctx -> clean(true)))
                        .then(Commands.literal("off").executes(ctx -> clean(false))))
                .then(Commands.literal("shot")
                        .then(Commands.argument("name", StringArgumentType.word()).executes(this::shot)))
                .then(Commands.literal("panorama")
                        .then(Commands.argument("name", StringArgumentType.word())
                                .then(Commands.argument("size", IntegerArgumentType.integer(16, PANORAMA_MAX))
                                        .executes(this::panorama)))));
    }

    // --- commands ----------------------------------------------------------

    private int ping() {
        var w = Minecraft.getInstance().getWindow();
        reply("ok " + version + " " + w.getWidth() + "x" + w.getHeight() + (clean ? " clean" : ""));
        return Command.SINGLE_SUCCESS;
    }

    private int clean(boolean on) {
        if (busy()) {
            return error("busy (a capture is running)");
        }
        clean = on;
        Minecraft.getInstance().options.hideGui = on;
        reply("clean " + (on ? "on" : "off"));
        return Command.SINGLE_SUCCESS;
    }

    private int shot(CommandContext<CommandSourceStack> ctx) {
        String name = StringArgumentType.getString(ctx, "name");
        String bad = check(name);
        if (bad != null) {
            return error(bad);
        }
        var mc = Minecraft.getInstance();
        shotName = name;
        shotFrames = 0;
        shotPrevHideGui = mc.options.hideGui;
        shotQueuedAt = System.nanoTime();
        mc.options.hideGui = true;
        return Command.SINGLE_SUCCESS;
    }

    private int panorama(CommandContext<CommandSourceStack> ctx) {
        String name = StringArgumentType.getString(ctx, "name");
        String bad = check(name);
        if (bad != null) {
            return error(bad);
        }
        panorama = new Panorama(name, IntegerArgumentType.getInteger(ctx, "size"));
        return Command.SINGLE_SUCCESS;
    }

    /** Null when a capture named {@code name} can start, else the reason. */
    private String check(String name) {
        if (!NAME.matcher(name).matches()) {
            return "bad name '" + name + "' (want [a-z0-9_-]{1,64})";
        }
        if (busy()) {
            return "busy (a capture is running)";
        }
        var mc = Minecraft.getInstance();
        if (mc.player == null || mc.level == null) {
            return "not in a world";
        }
        return null;
    }

    private boolean busy() {
        return shotName != null || panorama != null;
    }

    // --- frame events -------------------------------------------------------

    private void onFramePre(RenderFrameEvent.Pre event) {
        if (panorama != null) {
            try {
                panorama.beforeFrame();
            } catch (RuntimeException e) {
                failPanorama(e);
            }
        }
    }

    private void onFramePost(RenderFrameEvent.Post event) {
        if (shotName != null && ++shotFrames >= SETTLE_FRAMES) {
            finishShot();
        }
        if (panorama != null) {
            try {
                if (panorama.afterFrame()) {
                    Panorama p = panorama;
                    panorama = null;
                    p.restore();
                    reply("wrote " + p.rel + "/panorama_0..5.png (" + p.size + "x" + p.size + ") in " + ms(p.queuedAt)
                            + " ms" + (p.unsettled > 0 ? " (" + p.unsettled + " faces still compiling chunks)" : ""));
                }
            } catch (IOException | RuntimeException e) {
                failPanorama(e);
            }
        }
    }

    /** Shot: the GUI was hidden when the command ran; read a clean frame at the window size. */
    private void finishShot() {
        var mc = Minecraft.getInstance();
        String name = shotName;
        String rel = DIR + "/" + name + ".png";
        try (NativeImage img = Screenshot.takeScreenshot(mc.getMainRenderTarget())) {
            Path file = mc.gameDirectory.toPath().resolve(rel);
            Files.createDirectories(file.getParent());
            img.writeToFile(file);
            reply("wrote " + rel + " (" + img.getWidth() + "x" + img.getHeight() + ") in " + ms(shotQueuedAt) + " ms");
        } catch (IOException | RuntimeException e) {
            PexpDevtools.LOG.error("studio shot failed", e);
            error("shot " + name + ": " + e);
        } finally {
            mc.options.hideGui = clean || shotPrevHideGui;
            shotName = null;
        }
    }

    private void failPanorama(Exception e) {
        Panorama p = panorama;
        panorama = null;
        PexpDevtools.LOG.error("studio panorama failed", e);
        try {
            p.restore();
        } catch (RuntimeException e2) {
            PexpDevtools.LOG.error("studio panorama restore failed", e2);
        }
        error("panorama " + p.name + ": " + e);
    }

    /**
     * Six square faces in vanilla's order and orientation (as
     * {@code Minecraft.grabPanoramixScreenshot}: yaw +0/+90/+180/-90 level,
     * then up and down; 90 degree FOV). While it runs, every frame is rendered
     * at the face size (window size and main render target swapped, as
     * vanilla does) with the GUI hidden, panoramic mode on and the player
     * turned to the face. A face is read once {@link #SETTLE_FRAMES} frames
     * have rendered and the chunk sections in view are compiled, or after
     * {@link #FACE_SETTLE_MS}.
     */
    private final class Panorama {
        final String name;
        final int size;
        final String rel;
        final long queuedAt = System.nanoTime();
        int face;
        int frames;
        long faceStart;
        int unsettled;
        boolean started;
        // Saved state.
        int winW;
        int winH;
        float xRot;
        float yRot;
        float xRotO;
        float yRotO;
        boolean hideGui;

        Panorama(String name, int size) {
            this.name = name;
            this.size = size;
            this.rel = DIR + "/" + name;
        }

        void beforeFrame() {
            var mc = Minecraft.getInstance();
            var player = mc.player;
            if (player == null) {
                throw new IllegalStateException("left the world");
            }
            var window = mc.getWindow();
            if (!started) {
                winW = window.getWidth();
                winH = window.getHeight();
                xRot = player.getXRot();
                yRot = player.getYRot();
                xRotO = player.xRotO;
                yRotO = player.yRotO;
                hideGui = mc.options.hideGui;
                started = true;
                faceStart = System.nanoTime();
            }
            mc.options.hideGui = true;
            mc.gameRenderer.setRenderBlockOutline(false);
            mc.gameRenderer.setPanoramicMode(true);
            window.setWidth(size);
            window.setHeight(size);
            var target = mc.getMainRenderTarget();
            if (target.width != size || target.height != size) {
                target.resize(size, size, Minecraft.ON_OSX);
            }
            float y = switch (face) {
                case 1 -> (yRot + 90.0F) % 360.0F;
                case 2 -> (yRot + 180.0F) % 360.0F;
                case 3 -> (yRot - 90.0F) % 360.0F;
                default -> yRot;
            };
            float x = face == 4 ? -90.0F : face == 5 ? 90.0F : 0.0F;
            player.setYRot(y);
            player.setXRot(x);
            player.yRotO = y;
            player.xRotO = x;
        }

        /** Reads the face when it has settled; true when all six are written. */
        boolean afterFrame() throws IOException {
            if (!started) {
                return false;
            }
            var mc = Minecraft.getInstance();
            boolean settled = mc.levelRenderer.hasRenderedAllSections();
            boolean timedOut = System.nanoTime() - faceStart > FACE_SETTLE_MS * 1_000_000L;
            if (++frames < SETTLE_FRAMES || !(settled || timedOut)) {
                return false;
            }
            if (!settled) {
                unsettled++;
            }
            Path dir = mc.gameDirectory.toPath().resolve(rel);
            Files.createDirectories(dir);
            try (NativeImage img = Screenshot.takeScreenshot(mc.getMainRenderTarget())) {
                img.writeToFile(dir.resolve("panorama_" + face + ".png"));
            }
            face++;
            frames = 0;
            faceStart = System.nanoTime();
            return face == 6;
        }

        void restore() {
            if (!started) {
                return;
            }
            var mc = Minecraft.getInstance();
            var player = mc.player;
            if (player != null) {
                player.setXRot(xRot);
                player.setYRot(yRot);
                player.xRotO = xRotO;
                player.yRotO = yRotO;
            }
            mc.gameRenderer.setRenderBlockOutline(true);
            mc.gameRenderer.setPanoramicMode(false);
            mc.getWindow().setWidth(winW);
            mc.getWindow().setHeight(winH);
            mc.getMainRenderTarget().resize(winW, winH, Minecraft.ON_OSX);
            mc.options.hideGui = clean || hideGui;
        }
    }

    // --- replies -------------------------------------------------------------

    private static long ms(long since) {
        return (System.nanoTime() - since) / 1_000_000L;
    }

    private static int error(String reason) {
        reply("error " + reason);
        return 0;
    }

    /**
     * One {@code studio: ...} line as a system chat message: the chat listener
     * fires ClientChatReceivedEvent (MCPFabric's get_recent_chat records it)
     * and logs it to the client log as {@code [CHAT] studio: ...}.
     */
    private static void reply(String text) {
        String line = "studio: " + text;
        PexpDevtools.LOG.info(line);
        Minecraft.getInstance().getChatListener().handleSystemMessage(Component.literal(line), false);
    }
}
