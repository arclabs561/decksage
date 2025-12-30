# Testing Similar Cards with Your Trained Embeddings

## Status

✅ **Embeddings Found**: `data/embeddings/magic_128d_test_pecanpy.wv` (14MB)
✅ **Frontend Ready**: Similar cards feature implemented with API integration
✅ **Helper Script**: `start_api.sh` created to start API easily

## Quick Start

1. **Start the API**:
   ```bash
   ./start_api.sh
   # or
   python3 -m src.ml.api.api --embeddings data/embeddings/magic_128d_test_pecanpy.wv --port 8000
   ```

2. **Test in Browser**:
   - Open http://localhost:8080/test_search_hybrid.html
   - Search for a card
   - Click on a card image
   - See similar cards from your trained embeddings!

3. **Test API Directly**:
   ```bash
   curl 'http://localhost:8000/v1/cards/Lightning%20Bolt/similar?k=5'
   ```

## Features

- **API Integration**: Uses `/v1/cards/{name}/similar?k=12` endpoint
- **Fallback**: Mock data if API unavailable
- **Error Handling**: Timeout (3s), graceful degradation
- **Visual Feedback**: Loading states, error messages
- **Click to Search**: Click similar card to search for it

## Next Steps

1. Start API and verify card names match your embeddings
2. Test with real card names from your dataset
3. Verify similarity scores make sense
4. Consider grouping by similarity type (embedding, co-occurrence, etc.)

