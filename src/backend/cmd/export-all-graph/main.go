package main

import (
	"context"
	"fmt"
	"os"

	"collections/blob"
	"collections/games/magic/dataset"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
	limitlessweb "collections/games/pokemon/dataset/limitless-web"
	ygoprodecktournament "collections/games/yugioh/dataset/ygoprodeck-tournament"
	"collections/logger"
	"collections/transform/cardco"
)

func main() {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("INFO")

	if len(os.Args) < 2 {
		fmt.Println("Usage: go run main.go <output.csv>")
		os.Exit(1)
	}

	outputFile := os.Args[1]

	// Create blob bucket
	bucket, err := blob.NewBucket(ctx, log, "file://./data-full")
	if err != nil {
		log.Errorf(ctx, "Failed to create bucket: %v", err)
		os.Exit(1)
	}

	// Use the same prefix as the extract command: games/
	gamesBucket := bucket.WithPrefix("games/")

	// Create datasets
	var datasets []dataset.Dataset
	datasets = append(datasets, mtgtop8.NewDataset(log, gamesBucket))
	datasets = append(datasets, scryfall.NewDataset(log, gamesBucket))
	datasets = append(datasets, limitlessweb.NewDataset(log, gamesBucket))
	datasets = append(datasets, ygoprodecktournament.NewDataset(log, gamesBucket))

	// Create transform
	tr, err := cardco.NewTransform(ctx, log)
	if err != nil {
		log.Errorf(ctx, "Failed to create transform: %v", err)
		os.Exit(1)
	}
	defer tr.Close()

	// Run transform
	log.Infof(ctx, "Processing collections...")
	_, err = tr.Transform(ctx, datasets)
	if err != nil {
		log.Errorf(ctx, "Transform failed: %v", err)
		os.Exit(1)
	}

	// Export to CSV
	log.Infof(ctx, "Exporting to %s...", outputFile)
	err = tr.ExportCSV(ctx, outputFile)
	if err != nil {
		log.Errorf(ctx, "Export failed: %v", err)
		os.Exit(1)
	}

	fmt.Printf("\n✅ Successfully exported card co-occurrence graph to %s\n", outputFile)
}
