import Sortable from "sortablejs";

type SessionID = string;

type Tier = {
    is_d20: boolean;
    tier: number;
};

type Party = HTMLElement & {
    member_count: number;
    gm_of: [SessionID];
    tiers: { [key: SessionID]: Tier };
};

type SessionSlot = HTMLElement & {
    current_players: number;
    min_players: number;
    max_players: number;
    session: SessionID;
    session_member_list: SessionMemberList;
    session_member_count: SessionMemberCount;
};

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
        fromElement: SessionMemberList | HTMLElement,
        toElement: SessionMemberList | HTMLElement,
        evt: Sortable.SortableEvent | null = null,
    ) => {
        console.log("Emplacing party");
        console.log(party);

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
            party.dataset.tierValue = party.tiers[sessionSlot.session || ""]?.tier.toString() || "unknown";

            // If we are the GM, move to the top of the list
            // It is already in place so just move it to the front
            if (party.gm_of.includes(sessionSlot.session)) {
                sessionSlot.session_member_list.prepend(party);
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

        Sortable.create(sessionMemberList, options);

        sessionSlot.current_players = 0;
        sessionSlot.min_players = parseInt(sessionSlot.dataset.minPlayers || "0", 10);
        sessionSlot.max_players = parseInt(sessionSlot.dataset.maxPlayers || "0", 10);
        sessionSlot.session = sessionSlot.dataset.session || "";
        sessionSlot.session_member_list = sessionMemberList;
        sessionSlot.session_member_count = sessionMemberCount;

        sessionMemberList.typ = "member-list";
        sessionMemberList.session_slot = sessionSlot;
    }

    Sortable.create(unallocatedPartiesElement, options);

    for (const party of partyElements) {
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
};

export default event_manage_allocation;
