# RaidBot

Keeps track of channels you raid/host and channels that raid/host you.

You can also add channels manually.

Further the script offers an overlay that shows the current number of hosting channels and has a configurable goal that automatically
updates with new iterations of the goal.

The UI sorts your potential raid targets in reverse order of when you raided/hosted them last and shows which channel are currently online.

## Setup

* For the initial setup rename `clientid.conf.example` to `clientid.conf` and replace the line with your client id.
  * See the [Twitch Developers Documentation](https://dev.twitch.tv/docs/authentication/#registration) on how to get a client id.
* Also rename `OAuth.conf.example` to `OAuth.conf` and replace the example with an OAuth token that will allow the script to login to chat with the streamer-account.
  * You can get such a token from [Twitch Chat OAuth Password Generator](https://twitchapps.com/tmi)
* Insert the API Key file in the bot's script menu

### Overlay Styling Example

```css
body { background-color: rgba(0, 0, 0, 0); margin: 0px auto; overflow: hidden; }

.hostCount {
    background-color: rgba(200,200,200,0.5);
    font-size: 10em;
}

.hostCount::before {
    content: "Hosts: ";
}

div [is-complete="true"] {
    background-color: green;
}
```
