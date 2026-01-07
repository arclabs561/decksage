# Contributing

Thanks for contributing to ai-visual-test!

## Development Setup

```bash
# Clone the repository
git clone https://github.com/arclabs561/ai-visual-test.git
cd ai-visual-test

# Install dependencies (if any)
npm install
```

## Project Structure

```
ai-visual-test/
├── src/
│   ├── index.mjs          # Main exports
│   ├── judge.mjs          # VLLM judge
│   ├── config.mjs          # Configuration
│   ├── cache.mjs           # Caching
│   ├── multi-modal.mjs    # Multi-modal validation
│   ├── temporal.mjs       # Temporal aggregation
│   └── load-env.mjs       # Environment loader
├── example.test.mjs       # Example usage
└── README.md              # Documentation
```

## Making Changes

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Test your changes: `npm test`
4. Commit: `git commit -m "Add feature: your feature"`
5. Push: `git push origin feature/your-feature`
6. Open a Pull Request

## Code Style

- Use ES Modules (`.mjs` files)
- Follow existing code style
- Add JSDoc comments for public APIs
- Keep functions focused and testable

## Testing

- Add tests for new features
- Ensure all tests pass: `npm test`
- Test with different VLLM providers if possible

## Documentation

- Update README.md for new features
- Add examples to `example.test.mjs`
- Update CHANGELOG.md for user-facing changes

## Questions?

Open an issue on GitHub for questions or discussions.

