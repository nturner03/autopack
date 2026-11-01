package io.github.pexp.devtools;

import com.mojang.logging.LogUtils;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import org.slf4j.Logger;

/**
 * Agent test tooling for pack experiments. Never pack content: it registers no
 * blocks, items, registries or network payloads, so a client or server without
 * it can still connect.
 */
@Mod(PexpDevtools.MOD_ID)
public final class PexpDevtools {
    public static final String MOD_ID = "pexp_devtools";
    public static final Logger LOG = LogUtils.getLogger();

    public PexpDevtools(IEventBus modBus) {
        NeoForge.EVENT_BUS.addListener(DumpCommand::register);
    }
}
