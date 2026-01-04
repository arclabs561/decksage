package dataset

import (
	"collections/games/onepiece/game"
	"encoding/json"
)

// Package dataset provides One Piece specific dataset implementations.

// Item interface for One Piece dataset items (cards, decks, sets)
type Item interface {
	Kind() string
	item()
}

// CardItem wraps a One Piece card
type CardItem struct {
	Card *game.Card `json:"card"`
}

func (i *CardItem) Kind() string { return "Card" }
func (i *CardItem) item()        {}

// SetItem wraps a One Piece set/collection
type SetItem struct {
	Set *game.Collection `json:"set"`
}

func (i *SetItem) Kind() string { return "Set" }
func (i *SetItem) item()        {}

// DeserializeAsCard deserializes a One Piece card
func DeserializeAsCard(_ string, data []byte) (Item, error) {
	var card game.Card
	if err := json.Unmarshal(data, &card); err != nil {
		return nil, err
	}
	return &CardItem{Card: &card}, nil
}

// DeserializeAsSet deserializes a One Piece set
func DeserializeAsSet(_ string, data []byte) (Item, error) {
	var set game.Collection
	if err := json.Unmarshal(data, &set); err != nil {
		return nil, err
	}
	return &SetItem{Set: &set}, nil
}

