package io.github.pexp.devtools.gametest;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import io.github.pexp.devtools.Dump;
import io.github.pexp.devtools.PexpDevtools;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.neoforged.neoforge.gametest.GameTestHolder;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

/** The dump reflects the loaded game: vanilla data, NeoForge c: tags and a datapack-only recipe. */
@GameTestHolder(PexpDevtools.MOD_ID)
@PrefixGameTestTemplate(false)
public final class DumpTests {
    private DumpTests() {
    }

    private static JsonObject read(Path file) throws IOException {
        return JsonParser.parseString(Files.readString(file)).getAsJsonObject();
    }

    @GameTest(template = "empty")
    public static void dumpsLoadedData(GameTestHelper helper) {
        var server = helper.getLevel().getServer();
        Path dir = server.getServerDirectory().resolve("pexp/gametest-dump");
        try {
            Dump.Result r = Dump.run(server, dir);
            helper.assertTrue(r.recipes() > 1000, "expected >1000 recipes, got " + r.recipes());
            helper.assertTrue(r.recipeFailures() == 0, "vanilla recipes all encode, got " + r.recipeFailures() + " partial");
            helper.assertTrue(r.lootFailures() == 0, "vanilla loot all encodes, got " + r.lootFailures() + " failed");

            JsonObject recipes = read(dir.resolve("recipes.json"));
            JsonObject piston = recipes.getAsJsonObject("minecraft:piston");
            helper.assertTrue(piston != null, "minecraft:piston recipe present");
            helper.assertTrue("minecraft:crafting_shaped".equals(piston.get("type").getAsString()), "piston is shaped");
            helper.assertTrue("minecraft:piston".equals(
                    piston.getAsJsonObject("result").get("id").getAsString()), "piston result uses \"id\"");
            JsonObject marker = recipes.getAsJsonObject("pexp_devtools:gametest_marker");
            helper.assertTrue(marker != null, "datapack-only recipe present");
            helper.assertTrue(marker.getAsJsonObject("result").get("count").getAsInt() == 3, "marker count 3");

            JsonObject itemTags = read(dir.resolve("tags/item.json"));
            helper.assertTrue(itemTags.has("c:ingots/iron"), "c:ingots/iron present");
            helper.assertTrue(itemTags.getAsJsonArray("c:ingots/iron").toString().contains("minecraft:iron_ingot"),
                    "c:ingots/iron resolves to minecraft:iron_ingot");
            helper.assertTrue(itemTags.getAsJsonArray("minecraft:logs").toString().contains("minecraft:oak_log"),
                    "nested tag minecraft:logs is resolved to members");

            JsonObject loot = read(dir.resolve("loot.json"));
            helper.assertTrue(loot.has("minecraft:blocks/stone"), "minecraft:blocks/stone loot present");

            JsonObject meta = read(dir.resolve("meta.json"));
            helper.assertTrue(meta.getAsJsonObject("mods").has(PexpDevtools.MOD_ID), "meta lists loaded mods");
            helper.assertTrue(read(dir.resolve("ids.json")).getAsJsonArray("item").size() == r.items(), "ids count");
            helper.assertTrue(!Files.exists(dir.resolveSibling("gametest-dump.tmp")), "temp dir removed");
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        helper.succeed();
    }
}
