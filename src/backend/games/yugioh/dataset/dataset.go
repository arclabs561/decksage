package dataset

import (
	"collections/games/yugioh/game"
	"encoding/json"
)

// Package dataset provides Yu-Gi-Oh! specific dataset implementations.
//
// This package demonstrates the multi-game architecture by implementing
// the same patterns as games/magic/dataset but for Yu-Gi-Oh!
//
// Datasets:
//   - ygoprodeck: YGOPRODeck API (all cards)
//   - TODO: YGOPRODeck deck database
//   - TODO: DB.yugioh.com scraper

// Item interface for Yu-Gi-Oh! dataset items (cards, decks)
type Item interface {
	Kind() string
	item()
}

// CardItem wraps a Yu-Gi-Oh! card
type CardItem struct {
	Card *game.Card `json:"card"`
}

func (i *CardItem) Kind() string { return "Card" }
func (i *CardItem) item()        {}

// DeserializeAsCard deserializes a Yu-Gi-Oh! card
func DeserializeAsCard(_ string, data []byte) (Item, error) {
	var card game.Card
	if err := json.Unmarshal(data, &card); err != nil {
		return nil, err
	}
	return &CardItem{Card: &card}, nil
}
