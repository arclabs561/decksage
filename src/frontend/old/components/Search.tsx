import { h, render, Component } from 'preact';

class Search extends Component {
  state = { value = '' }

  onInput = ev => {
    this.setState({ value: ev.target.value });
  }

  // render() {
  //   return (
  //     <div>
  //       <h1>Search:</h1>
  //       <form>
  //         <input type="text" value={this.state.value} onInput={this.onInput} /input>
  //         <button type="submit">search</button>
  //       </form>
  //     </div>
  //   );
  // }
}
