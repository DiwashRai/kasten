# Setup

Once per machine. Needs `uv` and Python 3.12 or later; there are no other dependencies.

1. Copy this folder to `~/.claude/skills/relay`.
2. Install the command from the copy:

   ```
   uv tool install ~/.claude/skills/relay
   ```

   Or straight from GitHub, without a copy:

   ```
   uv tool install "git+https://github.com/DiwashRai/kasten#subdirectory=llm-context/relay"
   ```

3. Check it: `relay status` prints the daemon's state and the URL of the page that lists every
   thread.

To update, copy the folder again and add `--reinstall` to the install command, then run
`relay stop`. The next call starts the new version.

State is kept in `%LOCALAPPDATA%\relay\` (`~/.relay` elsewhere). `RELAY_PORT` changes the port from
47615 and `RELAY_HOME` the state folder.
