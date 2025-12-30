# Multi-Game Export Data Directory

## Issue

The `export-multi-game-graph` command expects a directory with `.zst` compressed collection files, but no such directory was found locally.

## Options

### Option 1: Use S3 (Recommended)
The collections are likely stored in S3 at `s3://games-collections/games/`. We could:
1. Download collections from S3 to a local directory
2. Run the export command on the local directory
3. Or modify the command to read directly from S3

### Option 2: Use Blob Storage
Other export commands use blob storage (`file://./data-full`). We could:
1. Create a `data-full` directory structure
2. Download collections from S3 to `data-full/games/`
3. Run the export command

### Option 3: Use Different Export Command
The `export-all-graph` command uses blob storage and handles multiple games. We could:
1. Use `export-all-graph` instead
2. It already supports MTG, YGO, and Pokemon
3. Outputs to CSV format

## Current Status

- ✅ Binary built: `bin/export-multi-game-graph`
- ❌ Data directory not found locally
- ✅ Collections available in S3: `s3://games-collections/games/`

## Next Steps

1. Check S3 for collection files
2. Download a sample to verify format
3. Either:
   - Download all collections locally, OR
   - Modify export command to read from S3

