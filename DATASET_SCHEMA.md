# Dataset Schema and Export Contract

This document defines the dataset formats for the Food.com synthetic adaptation pipeline.

## Core Principle

- `internal_master` is the audit ledger (quality, traceability, filtering).
- Mistral fine-tuning upload is `messages` only.

## 1) Internal Master Format (`data/internal_master.jsonl`)

One JSON object per line.

```json
{
  "source_recipe_id": "foodcom_12345",
  "source_recipe": {
    "title": "Mapo Tofu",
    "ingredients": [
      "400g tofu",
      "200g ground pork",
      "1 tsp oyster sauce",
      "1 tbsp doubanjiang"
    ],
    "steps": [
      "Brown pork in oil.",
      "Add doubanjiang and aromatics.",
      "Add tofu and simmer."
    ]
  },
  "target_restrictions": ["vegetarian"],
  "detected_violations": [
    {"ingredient": "ground pork", "reason": "meat_not_allowed"},
    {"ingredient": "oyster sauce", "reason": "animal_derived"}
  ],
  "replacement_pairs": [
    {"from": "ground pork", "to": "finely chopped shiitake + walnut", "reason": "texture_umami"},
    {"from": "oyster sauce", "to": "mushroom soy sauce", "reason": "umami"}
  ],
  "messages": [
    {
      "role": "system",
      "content": "You are a culinary adaptation assistant. Priority: (1) strict dietary compliance, (2) preserve dish identity and flavor profile, (3) keep instructions practical and cookable. Never include forbidden ingredients or their derivatives (stocks, sauces, pastes, broths). If no exact compliant substitute exists, acknowledge the gap, choose the closest viable option, and state the trade-off. Output sections exactly: Substitution Plan, Adapted Ingredients, Adapted Steps, Flavor Preservation Notes, Constraint Check."
    },
    {
      "role": "user",
      "content": "Recipe: Mapo Tofu\nIngredients: 400g firm tofu, 200g ground pork, 2 tbsp doubanjiang, 1 tbsp oyster sauce, 3 cloves garlic, 1 inch ginger, 2 scallions, 1 tbsp cornstarch, 2 tbsp neutral oil\nSteps: 1) Brown pork in oil. 2) Add aromatics and doubanjiang. 3) Add tofu and simmer. 4) Finish with cornstarch slurry. 5) Garnish with scallions.\nRestrictions: vegetarian"
    },
    {
      "role": "assistant",
      "content": "Substitution Plan:\n- ground pork -> 150g finely chopped shiitake + 50g crushed toasted walnuts (meaty chew + umami + fat richness)\n- oyster sauce -> 1 tbsp mushroom soy sauce + 0.5 tsp sugar (fermented depth + mild sweetness)\n\nAdapted Ingredients:\n- 400g firm tofu, cubed\n- 150g shiitake mushrooms, finely chopped\n- 50g walnuts, toasted and crushed\n- 2 tbsp doubanjiang\n- 1 tbsp mushroom soy sauce\n- 0.5 tsp sugar\n- 3 cloves garlic, minced\n- 1 inch ginger, minced\n- 2 scallions, sliced\n- 1 tbsp cornstarch + 2 tbsp water\n- 2 tbsp neutral oil\n\nAdapted Steps:\n1) Heat oil. Stir-fry shiitake and walnuts 3-4 min until browned.\n2) Add garlic, ginger, doubanjiang; stir-fry 30 sec.\n3) Add mushroom soy sauce and sugar; toss.\n4) Add tofu and 1 cup water; simmer 8 min.\n5) Stir in cornstarch slurry to thicken.\n6) Garnish with scallions.\n\nFlavor Preservation Notes:\n- Umami: shiitake glutamates + mushroom soy replace pork/oyster sauce umami. Doubanjiang remains primary driver.\n- Heat: mala profile intact via doubanjiang.\n- Texture: walnut crumble mimics rendered pork bits; shiitake adds chew.\n\nConstraint Check:\n- ground pork (meat): replaced with shiitake + walnut\n- oyster sauce (animal-derived): replaced with mushroom soy sauce + sugar\n- Derivative check: no meat stocks, fish sauces, or animal-derived pastes remain"
    }
  ],
  "template_id": "A",
  "audit_scores": {
    "constraint_pass": 1,
    "relevance_score": 0.81,
    "nontriviality_score": 0.88,
    "substitution_plausibility_score": 0.76,
    "semantic_completeness_pass": 1
  },
  "kept_for_training": true,
  "kb_version": "swaps_v0_2026-02-28",
  "generation_attempt_count": 1
}
```

### Required Fields

| Field | Why it is needed |
|---|---|
| `source_recipe_id` | Traceability and dedupe. |
| `source_recipe` | Recipe context for adaptation and relevance checks. |
| `target_restrictions` | Declares dietary goal to satisfy. |
| `detected_violations` | Explicit restricted/allergen violations in source. |
| `replacement_pairs` | Structured adaptation evidence (`from -> to`). |
| `messages` | Final training payload source. |
| `template_id` | Enforces prompt-variation tracking (`A`/`B`/`C`). |
| `audit_scores.*` | Deterministic pass/fail and ranking metrics. |
| `kept_for_training` | Include/exclude gate for export. |
| `kb_version` | Ties row to required substitution KB snapshot. |

### Optional Lightweight Field

| Field | Why it helps |
|---|---|
| `generation_attempt_count` | Distinguishes one-pass rows vs adaptive second-attempt rows. |

## 2) Adaptive Candidate Policy

Per source recipe:

1. Generate candidate 1.
2. Score candidate 1.
3. Generate candidate 2 only if candidate 1 fails either trigger:
   - `constraint_pass == 0`, or
   - `substitution_plausibility_score < 0.65`
4. Keep one winning candidate for that source recipe.

## 3) Deterministic Score Definitions

No extra judge API calls are required for these scores.

1. `constraint_pass` (`0/1`):
   - `1` only if restricted ingredients in `detected_violations` are removed/replaced and no banned terms remain.
2. `relevance_score` (`0-1`):
   - compare normalized ingredient names between source and adapted recipe, excluding restricted ingredients.
   - formula: `retained_nonrestricted_source_ingredients / total_nonrestricted_source_ingredients`.
3. `nontriviality_score` (`0-1`):
   - formula: `0.8 * (replaced_violations / max(1, total_violations)) + 0.2 * step_changed_flag`.
4. `substitution_plausibility_score` (`0-1`):
   - formula: `0.7 * kb_match_rate + 0.3 * valid_food_term_rate`.
5. `semantic_completeness_pass` (`0/1`):
   - `1` only if user content includes recipe title, ingredients, steps, and restrictions.

### Ingredient Normalization Rule (for relevance scoring)

Normalize ingredient strings with this fixed pipeline:

1. lowercase
2. strip quantities and units
3. remove parentheticals and prep adjectives
4. singularize tokens
5. alias-map known synonyms

## 4) Mistral Fine-Tuning Export (`data/train_filtered.jsonl`, `data/valid_filtered.jsonl`)

One JSON object per line.

### Rich Role Content Requirements

1. `system` content must include:
   - priority order: compliance -> dish identity/flavor -> practical usability
   - prohibition on forbidden ingredients and derivatives (stocks/sauces/pastes/broths)
   - hard fallback rule: if no exact compliant substitute exists, acknowledge the gap, choose closest viable option, and state the trade-off
   - required output sections: `Substitution Plan`, `Adapted Ingredients`, `Adapted Steps`, `Flavor Preservation Notes`, `Constraint Check`
2. `user` content must include:
   - recipe title, ingredients (with quantities), steps, restrictions/allergens
   - optional but recommended context: cuisine, must-keep flavor notes, pantry/time/equipment constraints
3. `assistant` content must include:
   - `Substitution Plan`: one row per detected violation (`from -> to -> why`). Every violation must be mapped. No missing entries.
   - `Adapted Ingredients`: full cookable ingredient list with quantities and units. No `...` and no "same as original." Standard culinary unit abbreviations (`g`, `kg`, `ml`, `l`, `tsp`, `tbsp`, `min`) are allowed.
   - `Adapted Steps`: full numbered steps reflecting all replacements. No source-step leftovers that reference removed ingredients.
   - `Flavor Preservation Notes`: at least 3 concrete mechanism notes covering distinct flavor dimensions (umami, heat, aroma, texture, fat, acid balance).
   - `Constraint Check`: explicit checklist of every resolved violation + derivative check result (stocks/sauces/pastes/broths confirmed absent).

### Richness Policy (Depth Tiers)

Keep semantics constant and vary phrasing/detail levels. All tiers must pass the same structural validation checks.

- **concise** (`10%`): all sections fully complete, shorter rationale per substitution, minimum 3 flavor notes. Same structural requirements — only prose density shrinks.
- **standard** (`70%`): full default detail level.
- **rich** (`20%`): standard + deeper flavor/technique explanation + optional alternative swap suggestion per substitution.

### Example: standard-depth export row

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a culinary adaptation assistant. Priority: (1) strict dietary compliance, (2) preserve dish identity and flavor profile, (3) keep instructions practical and cookable. Never include forbidden ingredients or their derivatives (stocks, sauces, pastes, broths). If no exact compliant substitute exists, acknowledge the gap, choose the closest viable option, and state the trade-off. Output sections exactly: Substitution Plan, Adapted Ingredients, Adapted Steps, Flavor Preservation Notes, Constraint Check."
    },
    {
      "role": "user",
      "content": "Recipe: Mapo Tofu\nCuisine: Sichuan Chinese\nIngredients: 400g firm tofu, 200g ground pork, 2 tbsp doubanjiang, 1 tbsp oyster sauce, 3 cloves garlic, 1 inch ginger, 2 scallions, 1 tbsp cornstarch, 2 tbsp neutral oil\nSteps: 1) Brown pork in oil until crispy. 2) Add minced garlic, ginger, and doubanjiang; stir-fry 30 seconds. 3) Add tofu cubes and 1 cup water; simmer 8 minutes. 4) Mix cornstarch slurry and stir in to thicken. 5) Garnish with sliced scallions.\nRestrictions: vegetarian, shellfish-free\nMust Keep Flavor Notes: mala heat, savory umami, silky sauce"
    },
    {
      "role": "assistant",
      "content": "Substitution Plan:\n- ground pork -> 150g finely chopped shiitake mushrooms + 50g crushed toasted walnuts (shiitake provides meaty chew and glutamate-driven umami; walnuts add fat richness and crumble texture similar to browned pork)\n- oyster sauce -> 1 tbsp mushroom soy sauce + 0.5 tsp sugar (mushroom soy supplies dark color and fermented depth; sugar compensates for the mild sweetness oyster sauce contributes)\n\nAdapted Ingredients:\n- 400g firm tofu, cut into 2cm cubes\n- 150g shiitake mushrooms, stems removed, finely chopped\n- 50g walnuts, toasted and roughly crushed\n- 2 tbsp doubanjiang\n- 1 tbsp mushroom soy sauce\n- 0.5 tsp sugar\n- 3 cloves garlic, minced\n- 1 inch ginger, minced\n- 2 scallions, sliced (white and green parts separated)\n- 1 tbsp cornstarch mixed with 2 tbsp water\n- 2 tbsp neutral oil\n\nAdapted Steps:\n1) Heat oil in a wok over high heat. Add chopped shiitake and crushed walnuts; stir-fry 3-4 minutes until mushrooms release moisture and edges brown.\n2) Add minced garlic, ginger, and scallion whites. Stir-fry 30 seconds until fragrant.\n3) Add doubanjiang and stir-fry 20 seconds to bloom in oil.\n4) Add mushroom soy sauce and sugar; toss to combine.\n5) Add tofu cubes gently and 1 cup water. Simmer 8 minutes without stirring to avoid breaking tofu.\n6) Drizzle cornstarch slurry around edges; gently fold until sauce thickens and coats tofu.\n7) Garnish with scallion greens.\n\nFlavor Preservation Notes:\n- Umami: shiitake glutamates + mushroom soy fermentation replace pork and oyster sauce umami sources. Doubanjiang (fermented bean paste) remains the primary flavor driver.\n- Heat: mala profile is fully intact — doubanjiang provides the la (numbing heat). Add Sichuan peppercorn if source recipe included it.\n- Texture: walnut crumble mimics the crispy rendered pork bits; shiitake provides chew. The sauce remains silky via the same cornstarch slurry technique.\n\nConstraint Check:\n- ground pork (meat): removed, replaced with shiitake + walnut\n- oyster sauce (shellfish-derived): removed, replaced with mushroom soy sauce + sugar\n- Derivative check: no meat stocks, fish sauces, or shellfish-derived pastes remain in adapted recipe"
    }
  ]
}
```

### Deterministic Assistant Completeness Validation

These checks run on every generated assistant response before it enters `internal_master`. Reject if any fail:

1. Reject if `...` appears anywhere in assistant content.
2. Reject if adapted ingredient list is not parseable or missing quantities.
3. Reject if any entry in `detected_violations` has no corresponding row in `Substitution Plan`.
4. Reject if any removed/banned ingredient still appears in `Adapted Ingredients` or `Adapted Steps`.

### Export Rules

1. Export only rows where:
   - `kept_for_training=true`
   - `audit_scores.constraint_pass=1`
   - `audit_scores.semantic_completeness_pass=1`
   - all 4 completeness validation checks pass
2. Do not include audit metadata in upload payload.
3. Keep metadata in `internal_master` for audit and reporting.
4. Do not serialize QC-only fields into roles (`audit_scores`, `template_id`, `kb_version`, `replacement_pairs` raw objects).

## 5) Prompt Variation Policy (Anti-Overfitting)

Use 3 user prompt templates with identical semantics. All three must pass `semantic_completeness_pass` (title, ingredients, steps, restrictions present).

Target mix on kept set: `50/30/20` (`+/-10` points per bucket).

Deterministic template assignment: `hash(source_recipe_id + primary_restriction) % 100` → `0-49` = A, `50-79` = B, `80-99` = C.

### Template A — Labeled Block (50%)

Structured, labeled fields. Most explicit format.

```
Recipe: {title}
Cuisine: {cuisine}
Ingredients: {ingredients_comma_separated}
Steps: {steps_numbered_inline}
Restrictions: {restrictions}
Must Keep Flavor Notes: {flavor_notes}
```

Example:
```
Recipe: Mapo Tofu
Cuisine: Sichuan Chinese
Ingredients: 400g firm tofu, 200g ground pork, 2 tbsp doubanjiang, 1 tbsp oyster sauce, 3 cloves garlic, 1 inch ginger, 2 scallions, 1 tbsp cornstarch, 2 tbsp neutral oil
Steps: 1) Brown pork in oil until crispy. 2) Add minced garlic, ginger, and doubanjiang; stir-fry 30 seconds. 3) Add tofu cubes and 1 cup water; simmer 8 minutes. 4) Mix cornstarch slurry and stir in to thicken. 5) Garnish with sliced scallions.
Restrictions: vegetarian, shellfish-free
Must Keep Flavor Notes: mala heat, savory umami, silky sauce
```

### Template B — Natural Request (30%)

Conversational prose. Same information, no rigid labels.

```
I have a recipe for {title} ({cuisine}) that I need to make {restrictions}-friendly.

The ingredients are: {ingredients_comma_separated}.

Here's how it's made: {steps_prose}

Please adapt it while keeping the dish recognizable.
```

Example:
```
I have a recipe for Mapo Tofu (Sichuan Chinese) that I need to make vegetarian and shellfish-free.

The ingredients are: 400g firm tofu, 200g ground pork, 2 tbsp doubanjiang, 1 tbsp oyster sauce, 3 cloves garlic, 1 inch ginger, 2 scallions, 1 tbsp cornstarch, 2 tbsp neutral oil.

Here's how it's made: Brown the pork in oil until crispy, then add minced garlic, ginger, and doubanjiang and stir-fry for 30 seconds. Add tofu cubes with a cup of water and simmer for 8 minutes. Thicken with a cornstarch slurry and garnish with sliced scallions.

Please adapt it while keeping the dish recognizable.
```

### Template C — Goal-Oriented (20%)

Leads with the dietary goal. Includes flavor preservation notes and optional practical constraints.

```
Goal: make {title} fully {restrictions}-compliant.

Source ingredients:
{ingredients_newline_list}

Source steps:
{steps_numbered_list}

Preserve these flavors: {flavor_notes}.
{optional_constraints}
```

Example:
```
Goal: make Mapo Tofu fully vegetarian and shellfish-free compliant.

Source ingredients:
- 400g firm tofu
- 200g ground pork
- 2 tbsp doubanjiang
- 1 tbsp oyster sauce
- 3 cloves garlic
- 1 inch ginger
- 2 scallions
- 1 tbsp cornstarch
- 2 tbsp neutral oil

Source steps:
1. Brown pork in oil until crispy.
2. Add minced garlic, ginger, and doubanjiang; stir-fry 30 seconds.
3. Add tofu cubes and 1 cup water; simmer 8 minutes.
4. Mix cornstarch slurry and stir in to thicken.
5. Garnish with sliced scallions.

Preserve these flavors: mala heat, savory umami, silky sauce.
Weeknight-friendly, under 30 minutes, no specialty equipment.
```

### Template format variation summary

| Dimension | Template A | Template B | Template C |
|---|---|---|---|
| Structure | Rigid labeled fields | Prose paragraphs | Goal-first + lists |
| Ingredient format | Comma-separated inline | Comma-separated inline | Newline bulleted list |
| Step format | Numbered inline `1) ...` | Narrative prose | Numbered list `1. ...` |
| Tone | Neutral/structured | Conversational | Directive |
| Cuisine tag | Always present | Parenthetical | Absent |
| Flavor notes | Labeled field | Absent (implied) | Explicit "Preserve these flavors" |
| Optional constraints | Absent | Absent | Present when available |

## 6) Required Knowledge Base (`kb/swaps_v0.json`)

`kb/swaps_v0.json` is required for v1 (not optional).

- Minimum size: 20-30 high-confidence swap rules.
- Scope: top constraints in project (`vegetarian`, `vegan`, `gluten_free`, etc.).

```json
{
  "version": "swaps_v0_2026-02-28",
  "rules": [
    {
      "rule_id": "veg_meat_to_mushroom_01",
      "applies_to_constraints": ["vegetarian", "vegan"],
      "match_terms": ["ground pork", "minced pork"],
      "replacement": ["finely chopped shiitake + toasted walnut"],
      "rationale": "Maintains texture and umami."
    }
  ]
}
```
