import Sortable from "sortablejs";

const event_manage_allocation = (scope_id: string) => {
    const scope = document.getElementById(scope_id);
    if (!scope) {
        console.error(`Scope with id ${scope_id} not found`);
        return;
    }
    console.log(`Scope: ${scope.id}`);

    const unallocatedPartiesElement = scope.querySelector(".unallocated-parties") as HTMLElement;
    const sessionMemberListElements = scope.querySelectorAll(".session-member-list") as NodeListOf<HTMLElement>;

    const options: Sortable.Options = {
        group: "allocation-shared",
        animation: 150,
        emptyInsertThreshold: 0,
        delay: 0,
        forceFallback: true,
        forceAutoScrollFallback: true,
    };

    for (const sessionMemberListElement of sessionMemberListElements) {
        Sortable.create(sessionMemberListElement, options);
    }

    Sortable.create(unallocatedPartiesElement, options);
};

export default event_manage_allocation;
