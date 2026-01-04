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
		fmt.Println("Usage: go run main.go <output.csv>")
		os.Exit(1)
	}

	_ = os.Args[1] // outputFile - TODO: implement CSV export

	// Create blob bucket
	bucket, err := blob.NewBucket(ctx, log, "file://./data-full")
	if err != nil {
		log.Errorf(ctx, "Failed to create bucket: %v", err)
		os.Exit(1)
	}

	// Use the same prefix as the extract command: games/
	gamesBucket := bucket.WithPrefix("games/")

	// Create datasets
	// Note: The transform expects games/magic/dataset.Dataset, but new games use games.Dataset
	// For now, only include MTG datasets and Pokemon limitless-web (which may need adapter)
	// TODO: Update transform to accept games.Dataset or create adapters
	var datasets []dataset.Dataset
	datasets = append(datasets, mtgtop8.NewDataset(log, gamesBucket))
	datasets = append(datasets, scryfall.NewDataset(log, gamesBucket))
	// limitlessweb implements games.Dataset, not magic/dataset.Dataset - may need adapter
	// datasets = append(datasets, limitlessweb.NewDataset(log, gamesBucket))
	// New games use games.Dataset - need transform update or adapters
	// datasets = append(datasets, digimonlimitless.NewDataset(log, gamesBucket))
	// datasets = append(datasets, onepiecelimitless.NewDataset(log, gamesBucket))
	// datasets = append(datasets, riftboundriftdecks.NewDataset(log, gamesBucket))

	// Create transform
	tr, err := cardco.NewTransform(ctx, log)
	if err != nil {
		log.Errorf(ctx, "Failed to create transform: %v", err)
		os.Exit(1)
	}
	// Note: Transform doesn't have Close() or ExportCSV() - this command needs updating
	// defer tr.close() // unexported method

	// Run transform
	log.Infof(ctx, "Processing collections...")
	_, err = tr.Transform(ctx, datasets)
	if err != nil {
		log.Errorf(ctx, "Transform failed: %v", err)
		os.Exit(1)
	}

	// TODO: Transform.ExportCSV() doesn't exist - need to implement or use different export method
	// For now, this command is incomplete
	log.Warnf(ctx, "Export functionality not yet implemented in transform")
	fmt.Printf("\n⚠️  Transform completed but CSV export not implemented\n")
}
