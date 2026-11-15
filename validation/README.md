# Validation

Notebooks that explore the data and check each backend function against reference tools before its result
is shown in the app. Use the kernel "SPHEREx Blink (validation)".

## Layout

```
notebooks/
  maxi/      Maxi's notebooks
  nico/      Nico's notebooks
  shared/    utils.py: helpers both use, until they move into backend/app/
```

## Naming

`NN_topic.ipynb`: two-digit number, lowercase English, underscores, no spaces or accents.
Examples: `01_coverage_map.ipynb`, `02_stack_eps_ind_b.ipynb`, `03_flags_recipe.ipynb`.

## Rules

- Each person edits only their own folder (notebooks merge badly). To build on someone else's, copy it.
- Clear outputs before committing.
- Reusable code goes into `backend/app/`, not here; notebooks import it from `app`.
- Commits: `(val: <type>): <description>`.
