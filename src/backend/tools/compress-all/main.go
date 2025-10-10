package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"

	"github.com/DataDog/zstd"
)

func main() {
	fmt.Println("🔧 COMPREHENSIVE FILE COMPRESSION")
	fmt.Println("==================================")
	fmt.Println()

	var (
		checked    atomic.Int64
		compressed atomic.Int64
		skipped    atomic.Int64
		errors     atomic.Int64
	)

	start := time.Now()

	// Collect all files first
	var files []string
	filepath.Walk("../../data-full/games/magic", func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".zst" {
			files = append(files, path)
		}
		return nil
	})

	fmt.Printf("Found %d .zst files to check\n", len(files))
	fmt.Println()

	// Process in parallel
	work := make(chan string, 100)
	wg := &sync.WaitGroup{}

	for i := 0; i < 16; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for path := range work {
				checked.Add(1)

				// Read first few bytes to check if compressed
				f, err := os.Open(path)
				if err != nil {
					errors.Add(1)
					continue
				}

				magic := make([]byte, 4)
				n, _ := f.Read(magic)
				f.Close()

				if n >= 4 && magic[0] == 0x28 && magic[1] == 0xB5 && magic[2] == 0x2F && magic[3] == 0xFD {
					// Already zstd compressed
					skipped.Add(1)
					continue
				}

				// Need to compress
				data, err := os.ReadFile(path)
				if err != nil {
					errors.Add(1)
					continue
				}

				compressed_data, err := zstd.Compress(nil, data)
				if err != nil {
					errors.Add(1)
					continue
				}

				if err := os.WriteFile(path, compressed_data, 0644); err != nil {
					errors.Add(1)
					continue
				}

				compressed.Add(1)

				if compressed.Load()%1000 == 0 {
					fmt.Printf("\rCompressed: %d  Skipped: %d  Errors: %d  Progress: %.1f%%",
						compressed.Load(), skipped.Load(), errors.Load(),
						100.0*float64(checked.Load())/float64(len(files)))
				}
			}
		}()
	}

	// Send work
	for _, path := range files {
		work <- path
	}
	close(work)
	wg.Wait()

	elapsed := time.Since(start)

	fmt.Printf("\r%s\n", "                                                                      ")
	fmt.Println()
	fmt.Println("==================================")
	fmt.Println("COMPRESSION COMPLETE")
	fmt.Println("==================================")
	fmt.Printf("✅ Compressed: %d\n", compressed.Load())
	fmt.Printf("⏭️  Already compressed: %d\n", skipped.Load())
	fmt.Printf("❌ Errors: %d\n", errors.Load())
	fmt.Printf("⏱️  Duration: %v\n", elapsed.Round(time.Second))
	fmt.Println()
}
