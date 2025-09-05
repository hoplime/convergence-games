import Sortable from "sortablejs";

type SessionID = string;
type UserID = string;

type Tier = {
    is_d20: boolean;
    tier: number;
};

type Party = HTMLElement & {
    leader: UserID;
    member_count: number;
    gm_of: [SessionID];
    tiers: { [key: SessionID]: Tier };
};

type SessionSlot = HTMLElement & {
    current_players: number;
    min_players: number;
    opt_players: number;
    max_players: number;
    session: SessionID;
    session_member_list: SessionMemberList;
    session_member_count: SessionMemberCount;
    session_member_count_displays: NodeListOf<HTMLElement>;
};

type SessionMemberList = HTMLElement & {
    typ: "member-list";
    session_slot: SessionSlot;
};

const isSessionMemberList = (element: HTMLElement): element is SessionMemberList => {
    return (element as SessionMemberList).typ === "member-list";
};

type SessionMemberCount = HTMLElement;

const updateSessionMemberCountDisplay = (sessionSlot: SessionSlot) => {
    sessionSlot.session_member_count.textContent = `${sessionSlot.current_players}/${sessionSlot.min_players}-${sessionSlot.max_players}`;
    if (
        sessionSlot.current_players < sessionSlot.min_players ||
        sessionSlot.current_players > sessionSlot.max_players
    ) {
        sessionSlot.session_member_count.classList.add("text-error");
        sessionSlot.session_member_count.classList.remove("text-success");
    } else {
        sessionSlot.session_member_count.classList.remove("text-error");
        sessionSlot.session_member_count.classList.add("text-success");
    }

    for (let i = 0; i < sessionSlot.session_member_count_displays.length; i++) {
        const display = sessionSlot.session_member_count_displays[i];
        if (i < sessionSlot.current_players) {
            display.classList.add("enabled");
        } else {
            display.classList.remove("enabled");
        }
    }
};

const event_manage_allocation = (scope_id: string) => {
    const scope = document.getElementById(scope_id);
    if (!scope) {
        console.error(`Scope with id ${scope_id} not found`);
        return;
    }
    console.log(`Scope: ${scope.id}`);

    const unallocatedPartiesElement = scope.querySelector(".unallocated-parties") as HTMLElement;
    const sessionSlotElements = scope.querySelectorAll(".session-slot") as NodeListOf<SessionSlot>;
    const partyElements = scope.querySelectorAll(".party") as NodeListOf<Party>;
    const saveButton = scope.querySelector(".save-button") as HTMLButtonElement;
    const commitButton = scope.querySelector(".commit-button") as HTMLButtonElement;

    const emplaceParty = (
        party: Party,
        fromElement: SessionMemberList | HTMLElement,
        toElement: SessionMemberList | HTMLElement,
    ) => {
        // Deal with FROM
        if (isSessionMemberList(fromElement)) {
            const sessionSlot = fromElement.session_slot;

            if (party.gm_of.includes(sessionSlot.session)) {
                // We were the GM of the session we just left
            } else {
                // We were a player of the session we just left
                sessionSlot.current_players -= party.member_count;
                updateSessionMemberCountDisplay(sessionSlot);
            }
        }

        // Deal with TO
        if (isSessionMemberList(toElement)) {
            const sessionSlot = toElement.session_slot;

            // If we are the GM, move to the top of the list
            // It is already in place so just move it to the front
            if (party.gm_of.includes(sessionSlot.session)) {
                // We are the GM of this session
                party.dataset.inGmGame = "true";
                sessionSlot.session_member_list.prepend(party);
            } else {
                // We are a player of this session
                sessionSlot.current_players += party.member_count;
                updateSessionMemberCountDisplay(sessionSlot);
                delete party.dataset.inGmGame;
                party.dataset.tierValue = party.tiers[sessionSlot.session || ""]?.tier.toString() || "unknown";
            }
        }
    };

    const options: Sortable.Options = {
        group: "allocation-shared",
        animation: 150,
        emptyInsertThreshold: 0,
        delay: 0,
        forceFallback: true,
        forceAutoScrollFallback: true,
        onEnd: (evt) => {
            console.log(`Moved item from ${evt.oldIndex} to ${evt.newIndex}`);

            const party = evt.item as Party;
            const fromElement = evt.from as SessionMemberList | HTMLElement;
            const toElement = evt.to as SessionMemberList | HTMLElement;

            emplaceParty(party, fromElement, toElement);
        },
    };

    // Do initial set up
    for (const sessionSlot of sessionSlotElements) {
        const sessionMemberList = sessionSlot.querySelector(".session-member-list") as SessionMemberList;
        const sessionMemberCount = sessionSlot.querySelector(".session-member-count") as SessionMemberCount;
        const sessionMemberCountDisplay = sessionSlot.querySelector(".session-member-count-display") as HTMLElement;

        Sortable.create(sessionMemberList, options);

        sessionSlot.current_players = 0;
        sessionSlot.min_players = parseInt(sessionSlot.dataset.minPlayers || "0", 10);
        sessionSlot.opt_players = parseInt(sessionSlot.dataset.optPlayers || "0", 10);
        sessionSlot.max_players = parseInt(sessionSlot.dataset.maxPlayers || "0", 10);
        sessionSlot.session = sessionSlot.dataset.session || "";
        sessionSlot.session_member_list = sessionMemberList;
        sessionSlot.session_member_count = sessionMemberCount;
        sessionSlot.session_member_count_displays = sessionMemberCountDisplay.querySelectorAll("div");

        sessionMemberList.typ = "member-list";
        sessionMemberList.session_slot = sessionSlot;
    }

    Sortable.create(unallocatedPartiesElement, options);

    for (const party of partyElements) {
        party.leader = party.dataset.leader || "";
        party.member_count = parseInt(party.dataset.memberCount || "0", 10);
        party.gm_of = JSON.parse(party.dataset.gmOf || "[]");
        party.tiers = JSON.parse(party.dataset.tiers || "{}");
    }

    // Emplace all the parties in their initial locations
    for (const party of partyElements) {
        const parentElement = party.closest(".session-member-list") as SessionMemberList | null;
        if (!parentElement) {
            continue;
        }
        // Place "from" unallocatedPartiesElement since we are just doing initial placement
        emplaceParty(party, unallocatedPartiesElement, parentElement);
    }

    const saveState = (commit: boolean) => {
        console.log(`Saving state ${commit ? "with" : "without"} commit`);
        // Gather state
        const allocations = Array.from(partyElements).map((party) => {
            const parentElement = party.closest(".session-slot") as SessionSlot | null;
            return {
                leader: party.dataset.leader || "",
                allocated_session: parentElement ? parentElement.session : null,
            };
        });

        console.log(allocations);
    };

    // Add event listeners to the buttons
    saveButton.addEventListener("click", () => {
        console.log("Save button clicked");
        if (confirm("Are you sure you want to save the current allocation?")) {
            saveState(false);
        }
    });
    commitButton.addEventListener("click", () => {
        console.log("Commit button clicked");
        if (confirm("Are you sure you want to commit the current allocation?")) {
            saveState(true);
        }
    });
};

export default event_manage_allocation;
