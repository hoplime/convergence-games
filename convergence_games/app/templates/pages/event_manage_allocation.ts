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

type SessionMemberList = HTMLElement & {
    typ: "member-list";
    session_slot: SessionSlot;
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
    const sessionSlots = scope.querySelectorAll(".session-slot") as NodeListOf<SessionSlot>;
    const parties = scope.querySelectorAll(".party") as NodeListOf<Party>;

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

            if ("typ" in fromElement && fromElement.typ === "member-list") {
                const sessionSlot = fromElement.session_slot;
                sessionSlot.current_players -= party.member_count;
                sessionSlot.session_member_count.textContent = `${sessionSlot.current_players}/${sessionSlot.min_players}-${sessionSlot.max_players}`;
            }

            if ("typ" in toElement && toElement.typ === "member-list") {
                const sessionSlot = toElement.session_slot;
                sessionSlot.current_players += party.member_count;
                sessionSlot.session_member_count.textContent = `${sessionSlot.current_players}/${sessionSlot.min_players}-${sessionSlot.max_players}`;
            }
        },
    };

    for (const sessionSlot of sessionSlots) {
        const sessionGM = sessionSlot.querySelector(".session-gm") as SessionGM;
        const sessionMemberList = sessionSlot.querySelector(".session-member-list") as SessionMemberList;
        const sessionMemberCount = sessionSlot.querySelector(".session-member-count") as SessionMemberCount;

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

    for (const party of parties) {
        party.member_count = parseInt(party.dataset.memberCount || "0", 10);
    }
};

export default event_manage_allocation;
