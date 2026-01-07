package game

import "collections/games"

// Ensure Collection implements games.CollectionAdapter
var _ games.CollectionAdapter = (*Collection)(nil)

func (c *Collection) GetID() string {
	return c.ID
}

func (c *Collection) GetURL() string {
	return c.URL
}

func (c *Collection) GetSource() string {
	// Magic Collection doesn't have Source field, return empty string
	// Source tracking is handled at the games.Collection level
	return ""
}

func (c *Collection) GetPartitions() []games.Partition {
	// Convert game.Partition to games.Partition
	result := make([]games.Partition, len(c.Partitions))
	for i, p := range c.Partitions {
		result[i] = games.Partition{
			Name: p.Name,
			Cards: make([]games.CardDesc, len(p.Cards)),
		}
		for j, card := range p.Cards {
			result[i].Cards[j] = games.CardDesc{
				Name:  card.Name,
				Count: card.Count,
			}
		}
	}
	return result
}

