package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"collections/games"

	"github.com/DataDog/zstd"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: go run main.go <deck-file.zst>")
		os.Exit(1)
	}

	path := os.Args[1]

	data, err := os.ReadFile(path)
	if err != nil {
		fmt.Printf("Error reading: %v\n", err)
		os.Exit(1)
	}

	decompressed, err := zstd.Decompress(nil, data)
	if err != nil {
		fmt.Printf("Error decompressing: %v\n", err)
		os.Exit(1)
	}

	var collection games.Collection
	if err := json.Unmarshal(decompressed, &collection); err != nil {
		fmt.Printf("Error parsing: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("File: %s\n", filepath.Base(path))
	fmt.Printf("Type: %s\n", collection.Type.Type)
	fmt.Printf("Source: %q\n", collection.Source)
	fmt.Printf("URL: %s\n", collection.URL)

	// Pretty print for inspection
	prettyJSON, _ := json.MarshalIndent(&collection, "", "  ")
	fmt.Printf("\n%s\n", string(prettyJSON[:min(len(prettyJSON), 2000)]))
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
