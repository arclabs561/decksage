package cmd

import (
	"collections/blob"
	"collections/logger"

	"github.com/spf13/cobra"
)

var migrateCmd = &cobra.Command{
	Use:  "migrate",
	RunE: runMigrate,
}

func init() {
	flags := migrateCmd.PersistentFlags()

	flags.String("log-level", "info", "level to log at")
	flags.String("bucket-url", "file://./data", "bucket url for writing dataset")
}
func runMigrate(cmd *cobra.Command, args []string) error {
	ctx := cmd.Context()
	log := logger.NewLogger(ctx)

	logLevel, err := cmd.Flags().GetString("log-level")
	if err != nil {
		panic(err)
	}
	log.SetLevel(logLevel)

	bucketUrl, err := cmd.Flags().GetString("bucket-url")
	if err != nil {
		panic(err)
	}

	blob, err := blob.NewBucket(ctx, log, bucketUrl)
	if err != nil {
		return err
	}

	if err := blob.Migrate(ctx); err != nil {
		return err
	}

	return nil
}
