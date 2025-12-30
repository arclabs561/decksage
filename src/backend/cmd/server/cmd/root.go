package cmd

import (
	"fmt"
	"net/http"
	"os"

	"github.com/spf13/cobra"
)

func Execute() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}

var rootCmd = &cobra.Command{
	Use:  "server",
	RunE: runRoot,
}

func init() {
	// rootCmd.AddCommand(extractCmd)
	// rootCmd.AddCommand(transformCmd)
	// rootCmd.AddCommand(migrateCmd)

	flags := rootCmd.PersistentFlags()
	_ = flags
}

func runRoot(cmd *cobra.Command, args []string) error {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("hello"))
	})
	http.ListenAndServe(":6000", handler)
	fmt.Println("HELLO")
	return nil
}
