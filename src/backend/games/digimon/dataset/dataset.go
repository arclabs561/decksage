package dataset

import (
	"collections/games/digimon/game"
	"encoding/json"
)

// Package dataset provides Digimon specific dataset implementations.

// Item interface for Digimon dataset items (cards, decks, sets)
type Item interface {
	Kind() string
	item()
}

// CardItem wraps a Digimon card
type CardItem struct {
	Card *game.Card `json:"card"`
}

func (i *CardItem) Kind() string { return "Card" }
func (i *CardItem) item()        {}

// SetItem wraps a Digimon set/collection
type SetItem struct {
	Set *game.Collection `json:"set"`
}

func (i *SetItem) Kind() string { return "Set" }
func (i *SetItem) item()        {}

// DeserializeAsCard deserializes a Digimon card
func DeserializeAsCard(_ string, data []byte) (Item, error) {
	var card game.Card
	if err := json.Unmarshal(data, &card); err != nil {
		return nil, err
	}
	return &CardItem{Card: &card}, nil
}

// DeserializeAsSet deserializes a Digimon set
func DeserializeAsSet(_ string, data []byte) (Item, error) {
	var set game.Collection
	if err := json.Unmarshal(data, &set); err != nil {
		return nil, err
	}
	return &SetItem{Set: &set}, nil
}

