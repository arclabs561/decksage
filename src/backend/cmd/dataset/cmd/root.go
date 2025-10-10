package cmd

import (
	"collections/blob"
	"collections/logger"
	"context"
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/felixge/fgprof"
	"github.com/spf13/cobra"
)

func Execute() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}

var rootCmd = &cobra.Command{
	Use:  "collections",
	RunE: runRoot,
}

func init() {
	flags := rootCmd.PersistentFlags()
	flags.String("log", "info", "level to log at")
	flags.String("bucket", "s3://games-collections", "bucket url for writing dataset")
	flags.StringP("cache", "c", "", "dir to use for local blob cache")
	flags.String("profile", "", "address to serve profiler at")

	rootCmd.AddCommand(extractCmd)
	rootCmd.AddCommand(transformCmd)
	rootCmd.AddCommand(indexCmd)
	rootCmd.AddCommand(catCmd)

	rootCmd.AddCommand(migrateCmd)
}

func runRoot(cmd *cobra.Command, args []string) error {
	return nil
}

type rootConfig struct {
	Ctx    context.Context
	Log    *logger.Logger
	Bucket *blob.Bucket
}

func newRootConfig(cmd *cobra.Command) (*rootConfig, error) {
	ctx := cmd.Context()
	log := logger.NewLogger(ctx)

	logLevel, err := cmd.Flags().GetString("log")
	if err != nil {
		return nil, fmt.Errorf("failed to get bool flag --log-level: %w", err)
	}
	log.SetLevel(logLevel)

	profileAddr, err := cmd.Flags().GetString("profile")
	if err != nil {
		return nil, err
	}
	if profileAddr != "" {
		http.DefaultServeMux.Handle("/debug/fgprof", fgprof.Handler())
		go func() {
			addr := profileAddr
			if strings.HasPrefix(profileAddr, ":") {
				addr = fmt.Sprintf("localhost%s", profileAddr)
			}
			log.Infof(ctx, "serving http profile on http://%s", addr)
			if err := http.ListenAndServe(profileAddr, nil); err != nil {
				log.Fatalf(ctx, "%v", err)
			}
		}()
	}

	bucketUrl, err := cmd.Flags().GetString("bucket")
	if err != nil {
		panic(err)
	}

	var bucketOpts []blob.BucketOption
	if cmd.Flags().Changed("cache") {
		cacheDir, err := cmd.Flags().GetString("cache")
		if err != nil {
			log.Fatalf(ctx, "failed to get flag --cache")
		}
		bucketOpts = append(bucketOpts, &blob.OptBucketCache{
			Dir: cacheDir,
		})
	}

	bucket, err := blob.NewBucket(ctx, log, bucketUrl, bucketOpts...)
	if err != nil {
		return nil, err
	}

	return &rootConfig{
		Ctx:    ctx,
		Log:    log,
		Bucket: bucket,
	}, nil
}
