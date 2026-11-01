package io.github.pexp.devtools;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.serialization.JsonOps;
import java.io.IOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Stream;
import net.minecraft.SharedConstants;
import net.minecraft.core.Holder;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.RegistryOps;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.Recipe;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.minecraft.world.level.storage.loot.LootTable;
import net.neoforged.fml.ModList;

/**
 * Writes what the server has actually loaded (after datapacks, KubeJS scripts
 * and every other reload listener) as JSON:
 *
 * <pre>
 * meta.json            when, game time, versions, counts, loaded mods
 * recipes.json         {recipe id: recipe JSON}, one entry per line
 * tags/&lt;registry&gt;.json  {tag id: [member ids]}, fully resolved; item, block, fluid, entity_type
 * loot.json            {loot table id: loot table JSON}, one entry per line
 * ids.json             {"item": [...], "block": [...], "fluid": [...], "entity_type": [...]}
 * </pre>
 *
 * Recipes and loot tables are re-encoded with the game's own codecs, so they
 * have the same shape as the JSON files in mod jars. A recipe whose codec can't
 * encode it (rare: some mods' special recipes) is written as {@code type}, its
 * result from {@code getResultItem} and {@code "_pexp_partial": "<error>"}.
 * The directory is replaced as a whole, so a reader never sees a half-written
 * dump.
 */
public final class Dump {
    private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().create();

    public record Result(int recipes, int recipeFailures, int tags, int lootTables, int lootFailures, int items,
            long millis, Path dir) {
    }

    private Dump() {
    }

    public static Result run(MinecraftServer server, Path dir) throws IOException {
        long start = System.currentTimeMillis();
        Path tmp = dir.resolveSibling(dir.getFileName() + ".tmp");
        deleteTree(tmp);
        Files.createDirectories(tmp.resolve("tags"));
        RegistryOps<JsonElement> ops = server.registryAccess().createSerializationContext(JsonOps.INSTANCE);

        // Recipes, as loaded.
        Map<String, JsonElement> recipes = new TreeMap<>();
        int recipeFailures = 0;
        for (RecipeHolder<?> holder : server.getRecipeManager().getRecipes()) {
            Recipe<?> recipe = holder.value();
            String id = holder.id().toString();
            var encoded = Recipe.CODEC.encodeStart(ops, recipe);
            if (encoded.result().isPresent()) {
                recipes.put(id, encoded.result().get());
            } else {
                recipeFailures++;
                recipes.put(id, partialRecipe(server, recipe,
                        encoded.error().map(e -> e.message()).orElse("encode failed")));
            }
        }
        writeEntries(tmp.resolve("recipes.json"), recipes);

        // Tags, resolved to member ids.
        int tags = 0;
        tags += writeTags(tmp.resolve("tags/item.json"), server.registryAccess().registryOrThrow(Registries.ITEM));
        tags += writeTags(tmp.resolve("tags/block.json"), server.registryAccess().registryOrThrow(Registries.BLOCK));
        tags += writeTags(tmp.resolve("tags/fluid.json"), server.registryAccess().registryOrThrow(Registries.FLUID));
        tags += writeTags(tmp.resolve("tags/entity_type.json"),
                server.registryAccess().registryOrThrow(Registries.ENTITY_TYPE));

        // Loot tables, as loaded.
        var lootRegistries = server.getServerResources().managers().fullRegistries();
        Map<String, JsonElement> loot = new TreeMap<>();
        int lootFailures = 0;
        for (ResourceLocation id : lootRegistries.getKeys(Registries.LOOT_TABLE)) {
            LootTable table = lootRegistries.getLootTable(ResourceKey.create(Registries.LOOT_TABLE, id));
            var encoded = LootTable.DIRECT_CODEC.encodeStart(ops, table);
            if (encoded.result().isPresent()) {
                loot.put(id.toString(), encoded.result().get());
            } else {
                lootFailures++;
                JsonObject stub = new JsonObject();
                stub.addProperty("_pexp_partial", encoded.error().map(e -> e.message()).orElse("encode failed"));
                loot.put(id.toString(), stub);
            }
        }
        writeEntries(tmp.resolve("loot.json"), loot);

        // Registry ids.
        JsonObject ids = new JsonObject();
        ids.add("item", idList(BuiltInRegistries.ITEM.keySet().stream()));
        ids.add("block", idList(BuiltInRegistries.BLOCK.keySet().stream()));
        ids.add("fluid", idList(BuiltInRegistries.FLUID.keySet().stream()));
        ids.add("entity_type", idList(BuiltInRegistries.ENTITY_TYPE.keySet().stream()));
        int items = ids.getAsJsonArray("item").size();
        Files.writeString(tmp.resolve("ids.json"), GSON.toJson(ids), StandardCharsets.UTF_8);

        long millis = System.currentTimeMillis() - start;
        JsonObject meta = new JsonObject();
        meta.addProperty("written_ms", System.currentTimeMillis());
        meta.addProperty("game_time", server.overworld().getGameTime());
        meta.addProperty("minecraft", SharedConstants.getCurrentVersion().getName());
        JsonObject counts = new JsonObject();
        counts.addProperty("recipes", recipes.size());
        counts.addProperty("recipes_partial", recipeFailures);
        counts.addProperty("tags", tags);
        counts.addProperty("loot_tables", loot.size());
        counts.addProperty("loot_tables_partial", lootFailures);
        counts.addProperty("items", items);
        meta.add("counts", counts);
        JsonObject mods = new JsonObject();
        ModList.get().getMods().stream()
                .sorted(Comparator.comparing(m -> m.getModId()))
                .forEach(m -> mods.addProperty(m.getModId(), m.getVersion().toString()));
        meta.add("mods", mods);
        meta.addProperty("millis", millis);
        Files.writeString(tmp.resolve("meta.json"), new GsonBuilder().setPrettyPrinting().create().toJson(meta),
                StandardCharsets.UTF_8);

        deleteTree(dir);
        Files.move(tmp, dir);
        return new Result(recipes.size(), recipeFailures, tags, loot.size(), lootFailures, items, millis, dir);
    }

    private static JsonObject partialRecipe(MinecraftServer server, Recipe<?> recipe, String error) {
        JsonObject out = new JsonObject();
        ResourceLocation serializer = BuiltInRegistries.RECIPE_SERIALIZER.getKey(recipe.getSerializer());
        out.addProperty("type", serializer == null ? "?" : serializer.toString());
        ResourceLocation type = BuiltInRegistries.RECIPE_TYPE.getKey(recipe.getType());
        out.addProperty("_pexp_recipe_type", type == null ? "?" : type.toString());
        try {
            ItemStack result = recipe.getResultItem(server.registryAccess());
            if (!result.isEmpty()) {
                JsonObject res = new JsonObject();
                res.addProperty("id", BuiltInRegistries.ITEM.getKey(result.getItem()).toString());
                res.addProperty("count", result.getCount());
                out.add("result", res);
            }
        } catch (RuntimeException e) {
            // Some special recipes have no fixed result.
        }
        out.addProperty("_pexp_partial", error);
        return out;
    }

    private static <T> int writeTags(Path file, Registry<T> registry) throws IOException {
        Map<String, JsonElement> out = new TreeMap<>();
        registry.getTags().forEach(pair -> {
            List<String> members = new ArrayList<>();
            for (Holder<T> holder : pair.getSecond()) {
                holder.unwrapKey().ifPresent(k -> members.add(k.location().toString()));
            }
            members.sort(null);
            JsonArray arr = new JsonArray();
            members.forEach(arr::add);
            out.put(pair.getFirst().location().toString(), arr);
        });
        writeEntries(file, out);
        return out.size();
    }

    private static JsonArray idList(Stream<ResourceLocation> ids) {
        JsonArray arr = new JsonArray();
        ids.map(ResourceLocation::toString).sorted().forEach(arr::add);
        return arr;
    }

    /** A JSON object with one entry per line, so files stay greppable. */
    private static void writeEntries(Path file, Map<String, JsonElement> entries) throws IOException {
        try (Writer w = Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
            w.write("{\n");
            int i = 0;
            for (var e : entries.entrySet()) {
                w.write(GSON.toJson(e.getKey()));
                w.write(": ");
                w.write(GSON.toJson(e.getValue()));
                w.write(++i < entries.size() ? ",\n" : "\n");
            }
            w.write("}\n");
        }
    }

    private static void deleteTree(Path path) throws IOException {
        if (!Files.exists(path)) {
            return;
        }
        try (Stream<Path> walk = Files.walk(path)) {
            for (Path p : walk.sorted(Comparator.reverseOrder()).toList()) {
                Files.delete(p);
            }
        }
    }
}
