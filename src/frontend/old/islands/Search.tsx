import { h, render, Component } from 'preact';

export default class Z extends Component {
  // Add `name` to the initial state
  state = { value: '', name: 'world' }

  onInput = ev => {
    console.log('onInput');
    this.setState({ value: ev.target.value });
  }

  // Add a submit handler that updates the `name` with the latest input value
  onSubmit = ev => {
    console.log('onSubmit');
    // Prevent default browser behavior (aka don't submit the form here)
    ev.preventDefault();

    this.setState({ name: this.state.value });

    this.search()
  }

  search() {
    console.log('search');
    let resp = fetch("http://localhost:6000/");
    console.log(resp);
    // console.log(resp.status); // 200
  }

  render() {
    return (
      <div>
        <h1>Hello, {this.state.name}!</h1>
        <form onSubmit={this.onSubmit}>
          <input type="text" class="border-2" value={this.state.value} onInput={this.onInput} />
        </form>
      </div>
    );
  }
}
