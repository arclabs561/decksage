package cmd

import (
	"strings"
	"testing"
)

func TestHealthRequiresExplicitStorage(t *testing.T) {
	rootCmd.SetArgs([]string{"health"})
	err := rootCmd.Execute()
	if err == nil || !strings.Contains(err.Error(), "--bucket is required") {
		t.Fatalf("expected explicit storage requirement before opening a bucket, got %v", err)
	}
}
