package dataset

import (
	"collections/games/riftbound/game"
	"encoding/json"
)

// Package dataset provides Riftbound specific dataset implementations.

// Item interface for Riftbound dataset items (cards, decks, sets)
type Item interface {
	Kind() string
	item()
}

// CardItem wraps a Riftbound card
type CardItem struct {
	Card *game.Card `json:"card"`
}

func (i *CardItem) Kind() string { return "Card" }
func (i *CardItem) item()        {}

// SetItem wraps a Riftbound set/collection
type SetItem struct {
	Set *game.Collection `json:"set"`
}

func (i *SetItem) Kind() string { return "Set" }
func (i *SetItem) item()        {}

// DeserializeAsCard deserializes a Riftbound card
func DeserializeAsCard(_ string, data []byte) (Item, error) {
	var card game.Card
	if err := json.Unmarshal(data, &card); err != nil {
		return nil, err
	}
	return &CardItem{Card: &card}, nil
}

// DeserializeAsSet deserializes a Riftbound set
func DeserializeAsSet(_ string, data []byte) (Item, error) {
	var set game.Collection
	if err := json.Unmarshal(data, &set); err != nil {
		return nil, err
	}
	return &SetItem{Set: &set}, nil
}
