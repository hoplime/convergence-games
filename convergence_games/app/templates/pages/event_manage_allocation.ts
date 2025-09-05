import Sortable from "sortablejs";

type Party = HTMLElement & {
    member_count: number;
};

type SessionSlot = HTMLElement & {
    current_players: number;
    min_players: number;
    max_players: number;
    session_gm: SessionGM;
    session_member_list: SessionMemberList;
    session_member_count: SessionMemberCount;
};

type SessionGM = HTMLElement & {
    typ: "gm";
    session_slot: SessionSlot;
};

// const is_session_gm = (element: HTMLElement): element is SessionGM => {
//     return (element as SessionGM).typ === "gm";
// };

type SessionMemberList = HTMLElement & {
    typ: "member-list";
    session_slot: SessionSlot;
};

const is_session_member_list = (element: HTMLElement): element is SessionMemberList => {
    return (element as SessionMemberList).typ === "member-list";
};

type SessionMemberCount = HTMLElement;

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

    const emplaceParty = (
        party: Party,
        fromElement: SessionGM | SessionMemberList | HTMLElement,
        toElement: SessionGM | SessionMemberList | HTMLElement,
    ) => {
        console.log(party);
        console.log(`Emplacing party from ${fromElement} to ${toElement}`);

        // Deal with FROM
        if (is_session_member_list(fromElement)) {
            const sessionSlot = fromElement.session_slot;
            sessionSlot.current_players -= party.member_count;
            sessionSlot.session_member_count.textContent = `${sessionSlot.current_players}/${sessionSlot.min_players}-${sessionSlot.max_players}`;
        }

        // Deal with TO
        if (is_session_member_list(toElement)) {
            const sessionSlot = toElement.session_slot;
            sessionSlot.current_players += party.member_count;
            sessionSlot.session_member_count.textContent = `${sessionSlot.current_players}/${sessionSlot.min_players}-${sessionSlot.max_players}`;
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
            const fromElement = evt.from as SessionGM | SessionMemberList | HTMLElement;
            const toElement = evt.to as SessionGM | SessionMemberList | HTMLElement;

            emplaceParty(party, fromElement, toElement);
        },
    };

    // Do initial set up
    for (const sessionSlot of sessionSlotElements) {
        const sessionGM = sessionSlot.querySelector(".session-gm") as SessionGM;
        const sessionMemberList = sessionSlot.querySelector(".session-member-list") as SessionMemberList;
        const sessionMemberCount = sessionSlot.querySelector(".session-member-count") as SessionMemberCount;

        Sortable.create(sessionGM, options);
        Sortable.create(sessionMemberList, options);

        sessionSlot.current_players = 0;
        sessionSlot.min_players = parseInt(sessionSlot.dataset.minPlayers || "0", 10);
        sessionSlot.max_players = parseInt(sessionSlot.dataset.maxPlayers || "0", 10);
        sessionSlot.session_gm = sessionGM;
        sessionSlot.session_member_list = sessionMemberList;
        sessionSlot.session_member_count = sessionMemberCount;

        sessionGM.typ = "gm";
        sessionGM.session_slot = sessionSlot;

        sessionMemberList.typ = "member-list";
        sessionMemberList.session_slot = sessionSlot;
    }

    Sortable.create(unallocatedPartiesElement, options);

    for (const party of partyElements) {
        party.member_count = parseInt(party.dataset.memberCount || "0", 10);
    }

    // Emplace all the parties in their initial locations
    for (const party of partyElements) {
        const parentElement = (party.closest(".session-member-list") ?? party.closest(".session-gm")) as
            | SessionGM
            | SessionMemberList
            | null;
        if (!parentElement) {
            console.error(`Party ${party.id} has no parent element`);
            continue;
        }
        // Place "from" unallocatedPartiesElement since we are just doing initial placement
        emplaceParty(party, unallocatedPartiesElement, parentElement);
    }
};

export default event_manage_allocation;
