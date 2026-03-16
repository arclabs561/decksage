package main

// Diagnose why metadata extraction fails
// This version actually reports errors instead of silently ignoring them

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/klauspost/compress/zstd"
)

func getKeys(m map[string]interface{}) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return keys
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: diagnose-metadata <data-dir>")
		os.Exit(1)
	}

	dataDir := os.Args[1]
	fmt.Println("Diagnosing metadata in:", dataDir)
	fmt.Println()

	var files []string
	filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".zst" {
			files = append(files, path)
		}
		return nil
	})

	fmt.Printf("Found %d .zst files\n", len(files))
	fmt.Println("Checking first 5 files...")

	stats := struct {
		total            int
		readErrors       int
		decompressErrors int
		jsonErrors       int
		noCollection     int
		hasArchetype     int
		hasFormat        int
	}{}

	for i, file := range files {
		if i >= 5 {
			break
		}

		fmt.Printf("[%d/%d] %s\n", i+1, len(files), filepath.Base(file))

		// Read file
		data, err := os.ReadFile(file)
		if err != nil {
			fmt.Printf("  ❌ Read error: %v\n\n", err)
			stats.readErrors++
			continue
		}

		// Decompress
		dec, err := zstd.NewReader(nil)
		if err != nil {
			fmt.Printf("  ❌ Decoder creation error: %v\n\n", err)
			stats.decompressErrors++
			continue
		}
		decompressed, err := dec.DecodeAll(data, nil)
		dec.Close()
		if err != nil {
			fmt.Printf("  ❌ Decompress error: %v\n\n", err)
			stats.decompressErrors++
			continue
		}

		// Parse JSON
		var obj map[string]interface{}
		if err := json.Unmarshal(decompressed, &obj); err != nil {
			fmt.Printf("  ❌ JSON parse error: %v\n\n", err)
			stats.jsonErrors++
			continue
		}

		// Check structure
		fmt.Printf("  📋 Root keys: %v\n", getKeys(obj))

		col, ok := obj["collection"].(map[string]interface{})
		if !ok {
			fmt.Printf("  ❌ No 'collection' field\n")
			// Show first 200 chars of JSON to understand structure
			jsonStr, _ := json.MarshalIndent(obj, "    ", "  ")
			if len(jsonStr) > 200 {
				fmt.Printf("  JSON preview: %s...\n\n", string(jsonStr[:200]))
			} else {
				fmt.Printf("  JSON: %s\n\n", string(jsonStr))
			}
			stats.noCollection++
			continue
		}

		// Check type field
		typeField, hasType := col["type"]
		if !hasType {
			fmt.Printf("  ⚠️  No 'type' field in collection\n\n")
			continue
		}

		// Check if type has inner
		typeMap, ok := typeField.(map[string]interface{})
		if !ok {
			fmt.Printf("  ⚠️  'type' is not a map: %T\n\n", typeField)
			continue
		}

		inner, hasInner := typeMap["inner"]
		if !hasInner {
			fmt.Printf("  ⚠️  No 'inner' field in type\n\n")
			continue
		}

		innerMap, ok := inner.(map[string]interface{})
		if !ok {
			fmt.Printf("  ⚠️  'inner' is not a map: %T\n\n", inner)
			continue
		}

		// Extract metadata
		archetype, _ := innerMap["archetype"].(string)
		format, _ := innerMap["format"].(string)

		fmt.Printf("  ✅ Archetype: '%s'\n", archetype)
		fmt.Printf("  ✅ Format: '%s'\n", format)

		if archetype != "" {
			stats.hasArchetype++
		}
		if format != "" {
			stats.hasFormat++
		}

		stats.total++
		fmt.Println()
	}

	// Summary
	fmt.Println("============================================================")
	fmt.Println("DIAGNOSIS SUMMARY:")
	fmt.Printf("  Total processed: %d\n", stats.total)
	fmt.Printf("  Read errors: %d\n", stats.readErrors)
	fmt.Printf("  Decompress errors: %d\n", stats.decompressErrors)
	fmt.Printf("  JSON parse errors: %d\n", stats.jsonErrors)
	fmt.Printf("  No collection field: %d\n", stats.noCollection)
	fmt.Printf("  With archetype: %d\n", stats.hasArchetype)
	fmt.Printf("  With format: %d\n", stats.hasFormat)
	fmt.Println()

	if stats.total == 0 {
		fmt.Println("❌ FAILED: No files could be processed")
		fmt.Println("   Check file format or decompression")
	} else if stats.hasArchetype == 0 {
		fmt.Println("⚠️  ISSUE: Files parse but no metadata found")
		fmt.Println("   Check if Go scraper is extracting metadata correctly")
	} else {
		fmt.Printf("✅ SUCCESS: %d/%d files have metadata\n", stats.hasArchetype, stats.total)
		fmt.Println("   Metadata exists in files!")
	}
}
