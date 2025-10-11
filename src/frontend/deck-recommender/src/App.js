import logo from './logo.svg';
import './App.css';
import React, { useState } from 'react';

function App() {
  const [searchText, setSearchText] = useState('');
  const [selectedCards, setSelectedCards] = useState([]);

  const handleSearch = (e) => {
    setSearchText(e.target.value);
    console.log('search text is now', searchText);
    // Implement the logic for searching cards using the Meilisearch backend
  };

  const handleCardSelection = (card) => {
    setSelectedCards([...selectedCards, card]);
    // Implement the logic for updating the recommended cards list
  };

  return (
    <div className="App">
      <header>
        <h1>Deck Building Recommender</h1>
      </header>
      <div className="search-box">
        <input
          type="text"
          placeholder="Search for cards"
          value={searchText}
          onChange={handleSearch}
        />
      </div>
      <div className="results">
        {/* Implement the component to display search results */}
      </div>
    </div>
  );
}

export default App;
