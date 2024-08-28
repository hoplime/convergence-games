# Bugs - Backend

# Bugs - Frontend

- [x] The profile cancel edit buttons etc break the page #content because of the hx-target based replacements and block logic
- [ ] After sign up, you don't get an updated nav bar

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
- [ ] Reimporting from spreadsheet
- [ ] Update caching for game updates
- [ ] Make commit actually do something
- [ ] Keep group preferences together after an allocation even if the group changes (ahh we need a Group table concept or something)
- [ ] Enforce D20s in groups properly
- [ ] Do the commits

# Features - Frontend

- [x] Check in? Or does this just need to be on the backend
- [ ] Let people know what games they're in
- [x] Display smaller room games
- [ ] Show GMs as "players" in player allocation
- [ ] Group UI
- [ ] Show people that aren't checked in at all
- [ ] Show people that are checked in but not allocated
- [ ] Show people the games they're in
- [ ] Update the home page
- [ ] Design changes based on Jane's feedback
