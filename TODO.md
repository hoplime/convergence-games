# Bugs - Backend

# Bugs - Frontend

- [x] The profile cancel edit buttons etc break the page #content because of the hx-target based replacements and block logic
- [x] After sign up, you don't get an updated nav bar
- [x] Check in status not properly updating when time slot changes
- [x] In schedule view, going to a game and then backing out doesn't (visually) preserve ratings
- [x] Have to toggle dark theme/light theme to fix colors of ratings?
- [x] Allow submit with enter/regular submit on group interactions
- [x] Can't correctly reallocate on any time slot other than the first
- [x] Refreshing the page on schedule doesn't keep the drop down state

# Features - Algorithm

- [x] Deal with games which don't end up with enough players
- [x] Deal with the case where there are too many games
- [x] D20s
- [x] Multiple people in a group
- [x] Don't allocate non checked in GMs
- [x] Don't allocate people to games where the GM isn't checked in either
- [ ] Annealing based swapping trials?
- [x] LOCK IN AND APPLY
  - [x] Actually spending D20s
  - [x] Actually granting compensation

# Features - Backend + DB

- [x] Maintaining database between restarts
- [x] Run the allocation
  - [x] Don't try to allocate GMs during their sessions lol
- [x] Not painful table shifting from admins
- [x] Importing game schedule from spreadsheet
- [x] Database backing up
- [x] Make commit actually do something
- [x] Keep group preferences together after an allocation even if the group changes (ahh we need a Group table concept or something)
- [x] Do the commits
- [x] Disallow editing group members if you're committed
- [x] Allow force checking in/out people
- [x] Enforce D20s in groups properly
- [ ] Reimporting from spreadsheet
- [ ] Update caching for game updates

# Features - Frontend

- [x] Check in? Or does this just need to be on the backend
- [x] Let people know what games they're in
- [x] Display smaller room games
- [x] Show GMs as "players" in player allocation
- [x] Group UI
- [x] Show people that aren't checked in at all
- [x] Show people that are checked in but not allocated
- [x] Show people the games they're in
- [x] Allow leaving groups
- [x] Improve feedback for sign up related errors
- [x] Improve feedback for not having an API-Key lol
- [x] Sticky api-key and actions?
- [x] Easy way to deal with people/D20s etc
- [x] Display private rooms
- [x] Update the room names
- [x] Update the home page
- [ ] Design changes based on Jane's feedback
