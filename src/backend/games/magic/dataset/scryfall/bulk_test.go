package scryfall

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// The index field and gzip/JSONL framing follow https://scryfall.com/docs/api/bulk-data.
// Card names are synthetic; no live bulk archive is required by these tests.
func TestDownloadBulkCardsFormatsAndLimit(t *testing.T) {
	for _, tc := range []struct {
		name  string
		jsonl bool
		body  string
	}{
		{"jsonl", true, "{\"name\":\"first\"}\n{\"name\":\"second\"}\n"},
		{"legacy", false, "[{\"name\":\"first\"},{\"name\":\"second\"}]"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var body bytes.Buffer
			if tc.jsonl {
				gz := gzip.NewWriter(&body)
				if _, err := gz.Write([]byte(tc.body)); err != nil {
					t.Fatal(err)
				}
				if err := gz.Close(); err != nil {
					t.Fatal(err)
				}
			} else {
				body.WriteString(tc.body)
			}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Header.Get("User-Agent") == "" {
					t.Error("missing User-Agent")
				}
				_, _ = w.Write(body.Bytes())
			}))
			defer server.Close()
			for _, limit := range []int{-1, 0, 1} {
				cards, err := downloadBulkCards(context.Background(), server.URL, tc.jsonl, limit)
				if err != nil {
					t.Fatal(err)
				}
				want := limit
				if want < 0 {
					want = 2
				}
				if len(cards) != want {
					t.Fatalf("limit %d: got %d cards, want %d", limit, len(cards), want)
				}
				if len(cards) > 0 && cards[0].Name != "first" {
					t.Fatalf("unexpected first card: %+v", cards[0])
				}
				if len(cards) == 2 && cards[1].Name != "second" {
					t.Fatalf("unexpected second card: %+v", cards[1])
				}
			}
		})
	}
}

func TestBulkIndexJSONLField(t *testing.T) {
	var index respBulkData
	if err := json.Unmarshal([]byte(`{"data":[{"type":"default_cards","jsonl_download_uri":"https://example.test/cards.jsonl.gz"}]}`), &index); err != nil {
		t.Fatal(err)
	}
	if index.Data[0].JSONLDownloadURI != "https://example.test/cards.jsonl.gz" {
		t.Fatal("lost JSONL download URI")
	}
}

func TestDownloadBulkCardsRejectsMalformedBody(t *testing.T) {
	for _, jsonl := range []bool{true, false} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			_, _ = w.Write([]byte("not a bulk archive"))
		}))
		_, err := downloadBulkCards(context.Background(), server.URL, jsonl, -1)
		server.Close()
		if err == nil {
			t.Fatalf("jsonl=%t: accepted malformed body", jsonl)
		}
	}
}

func TestDownloadBulkCardsStopsDecodingAtLimit(t *testing.T) {
	var body bytes.Buffer
	gz := gzip.NewWriter(&body)
	if _, err := gz.Write([]byte("{\"name\":\"first\"}\ninvalid later record")); err != nil {
		t.Fatal(err)
	}
	if err := gz.Close(); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(body.Bytes())
	}))
	defer server.Close()
	cards, err := downloadBulkCards(context.Background(), server.URL, true, 1)
	if err != nil || len(cards) != 1 {
		t.Fatalf("limited download: cards=%v err=%v", cards, err)
	}
	if _, err := downloadBulkCards(context.Background(), server.URL, true, -1); err == nil {
		t.Fatal("unlimited download accepted malformed later record")
	}
}
