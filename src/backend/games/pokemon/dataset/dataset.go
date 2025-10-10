package dataset

import (
	"collections/games/pokemon/game"
	"encoding/json"
)

// Package dataset provides Pokemon specific dataset implementations.
//
// This package demonstrates the multi-game architecture by implementing
// the same patterns as games/magic/dataset but for Pokemon TCG.
//
// Datasets:
//   - pokemontcg: Pokemon TCG API (official cards and sets)
//   - TODO: Limitless TCG scraper (tournament decks)
//   - TODO: PokeBeach scraper (news and decks)

// Item interface for Pokemon dataset items (cards, decks, sets)
type Item interface {
	Kind() string
	item()
}

// CardItem wraps a Pokemon card
type CardItem struct {
	Card *game.Card `json:"card"`
}

func (i *CardItem) Kind() string { return "Card" }
func (i *CardItem) item()        {}

// SetItem wraps a Pokemon set/collection
type SetItem struct {
	Set *game.Collection `json:"set"`
}

func (i *SetItem) Kind() string { return "Set" }
func (i *SetItem) item()        {}

// DeserializeAsCard deserializes a Pokemon card
func DeserializeAsCard(_ string, data []byte) (Item, error) {
	var card game.Card
	if err := json.Unmarshal(data, &card); err != nil {
		return nil, err
	}
	return &CardItem{Card: &card}, nil
}

// DeserializeAsSet deserializes a Pokemon set
func DeserializeAsSet(_ string, data []byte) (Item, error) {
	var set game.Collection
	if err := json.Unmarshal(data, &set); err != nil {
		return nil, err
	}
	return &SetItem{Set: &set}, nil
}
