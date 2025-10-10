package main

import (
	"context"
	"fmt"
	"os"

	"collections/blob"
	"collections/games/magic/dataset"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
	"collections/logger"
	"collections/transform/cardco"
)

func main() {
	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("INFO")

	if len(os.Args) < 2 {
		fmt.Println("Usage: go run main.go <pairs.csv>")
		os.Exit(1)
	}

	pairsFile := os.Args[1]

	// Create blob bucket
	bucket, err := blob.NewBucket(ctx, log, "file://./data-full")
	if err != nil {
		log.Errorf(ctx, "Failed to create bucket: %v", err)
		os.Exit(1)
	}

	gamesBucket := bucket.WithPrefix("games/")

	// Create datasets
	var datasets []dataset.Dataset
	datasets = append(datasets, mtgtop8.NewDataset(log, gamesBucket))
	datasets = append(datasets, scryfall.NewDataset(log, gamesBucket))

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

	// Export pairs CSV
	log.Infof(ctx, "Exporting pairs to %s...", pairsFile)
	err = tr.ExportCSV(ctx, pairsFile)
	if err != nil {
		log.Errorf(ctx, "Export failed: %v", err)
		os.Exit(1)
	}

	// Also export attributes CSV next to pairs.csv
	attrFile := pairsFile
	if len(attrFile) >= 4 && attrFile[len(attrFile)-4:] == ".csv" {
		attrFile = attrFile[:len(attrFile)-4] + "_card_attributes.csv"
	} else {
		attrFile = attrFile + "_card_attributes.csv"
	}

	log.Infof(ctx, "Exporting attributes to %s...", attrFile)
	if err := tr.ExportAttributesCSV(ctx, attrFile); err != nil {
		log.Errorf(ctx, "Export attributes failed: %v", err)
		os.Exit(1)
	}

	fmt.Printf("\n✅ Exported pairs to %s and attributes to %s\n", pairsFile, attrFile)
}
