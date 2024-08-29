# Bugs - Backend

# Bugs - Frontend

- [x] The profile cancel edit buttons etc break the page #content because of the hx-target based replacements and block logic
- [x] After sign up, you don't get an updated nav bar
- [x] Check in status not properly updating when time slot changes

# Features - Algorithm

- [x] Deal with games which don't end up with enough players
- [x] Deal with the case where there are too many games
- [x] D20s
- [x] Multiple people in a group
- [ ] Annealing based swapping trials?

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
- [ ] Enforce D20s in groups properly
- [ ] Disallow editing group members if you're committed
- [ ] Reimporting from spreadsheet
- [ ] Update caching for game updates
- [ ] Allow force checking in/out people

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
- [ ] Update the home page
- [ ] Design changes based on Jane's feedback
