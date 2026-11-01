package io.github.pexp.devtools;

import com.mojang.brigadier.Command;
import com.mojang.brigadier.context.CommandContext;
import java.nio.file.Path;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.neoforged.neoforge.event.RegisterCommandsEvent;

/**
 * {@code /pexp dump}: write the server's loaded recipes, tags, loot tables and
 * registry ids to {@code <server dir>/pexp/dump/}. Op level 2. The reply is one
 * line, starting {@code pexp: dumped} or {@code pexp: error}, which
 * {@code scripts/recipe_index.py build --live} reads through MCPFabric.
 */
final class DumpCommand {
    static final String DIR = "pexp/dump";

    private DumpCommand() {
    }

    static void register(RegisterCommandsEvent event) {
        event.getDispatcher().register(Commands.literal("pexp")
                .requires(src -> src.hasPermission(2))
                .then(Commands.literal("dump").executes(DumpCommand::dump)));
    }

    private static int dump(CommandContext<CommandSourceStack> ctx) {
        var server = ctx.getSource().getServer();
        Path dir = server.getServerDirectory().resolve(DIR);
        try {
            Dump.Result r = Dump.run(server, dir);
            String line = "pexp: dumped " + r.recipes() + " recipes (" + r.recipeFailures() + " encoded partially), "
                    + r.tags() + " tags, " + r.lootTables() + " loot tables (" + r.lootFailures()
                    + " failed), " + r.items() + " items to " + DIR + " in " + r.millis() + " ms";
            ctx.getSource().sendSuccess(() -> Component.literal(line), false);
            PexpDevtools.LOG.info(line);
            return Command.SINGLE_SUCCESS;
        } catch (Exception e) {
            PexpDevtools.LOG.error("pexp dump failed", e);
            ctx.getSource().sendFailure(Component.literal("pexp: error " + e));
            return 0;
        }
    }
}
