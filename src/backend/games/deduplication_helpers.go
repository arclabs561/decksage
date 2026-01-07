package games

// CollectionAdapter adapts game-specific Collection types to universal Collection for deduplication
type CollectionAdapter interface {
	GetID() string
	GetURL() string
	GetSource() string
	GetPartitions() []Partition
}

// ConvertToUniversalCollection converts a game-specific collection to universal Collection
// This is a helper for deduplication which works on the universal Collection type
func ConvertToUniversalCollection(adapter CollectionAdapter) *Collection {
	return &Collection{
		ID:          adapter.GetID(),
		URL:         adapter.GetURL(),
		Source:      adapter.GetSource(),
		Partitions:  adapter.GetPartitions(),
	}
}

// FindDuplicateForAdapter checks for duplicates using an adapter
func (dt *DeduplicationTracker) FindDuplicateForAdapter(adapter CollectionAdapter) (isDuplicate bool, canonicalID, canonicalURL string) {
	universal := ConvertToUniversalCollection(adapter)
	return dt.FindDuplicate(universal)
}

