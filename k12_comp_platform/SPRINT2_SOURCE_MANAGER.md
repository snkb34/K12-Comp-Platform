# Sprint 2: Source Manager

## What this patch adds

- New `/source-manager` page
- Add Source form with expanded metadata
- Master CSV import support
- Master CSV export
- Navigation link for Source Manager
- Backward compatibility with the original CSV format

## Files

Place files here:

- `main.py` → `k12_comp_platform/app/main.py`
- `base.html` → `k12_comp_platform/app/templates/base.html`
- `index.html` → `k12_comp_platform/app/templates/index.html`
- `source_manager.html` → `k12_comp_platform/app/templates/source_manager.html`

## After deployment

1. Open `/source-manager`
2. Upload the master source CSV
3. Check "Replace existing source list" if you want the master list to become the source of truth
4. Click "Run Update" from the Dashboard
