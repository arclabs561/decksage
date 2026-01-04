package cmd

import (
	"context"
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"collections/games"
)

var statsCmd = &cobra.Command{
	Use:   "stats",
	Short: "Export extraction statistics",
	Long:  "Export extraction statistics from a previous run to JSON format",
	RunE:  runStats,
}

func init() {
	statsCmd.Flags().String("output", "", "Output file for JSON statistics (default: stdout)")
}

func runStats(cmd *cobra.Command, args []string) error {
	config, err := newRootConfig(cmd)
	if err != nil {
		return err
	}

	// For now, this is a placeholder that shows how stats export would work
	// In a real implementation, stats would be loaded from a previous extraction
	stats := games.NewExtractStats(config.Log)

	// Example: simulate some stats
	stats.RecordSuccess()
	stats.RecordSuccess()
	stats.RecordError(context.Background(), "http://example.com/error", "test", fmt.Errorf("test error"))
	stats.RecordNormalization()
	stats.RecordCacheHit()
	stats.RecordCacheMiss()

	output, err := cmd.Flags().GetString("output")
	if err != nil {
		return err
	}

	jsonData, err := stats.ExportJSON()
	if err != nil {
		return fmt.Errorf("failed to export stats: %w", err)
	}

	if output == "" {
		fmt.Println(string(jsonData))
	} else {
		if err := os.WriteFile(output, jsonData, 0644); err != nil {
			return fmt.Errorf("failed to write stats file: %w", err)
		}
		fmt.Printf("Statistics exported to %s\n", output)
	}

	return nil
}
