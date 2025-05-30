import Sortable from "sortablejs";

const event_manage_schedule = (scope_id: string) => {
    const scope = document.getElementById(scope_id);
    if (!scope) {
        console.error(`Scope with id ${scope_id} not found`);
        return;
    }
    const scheduleTableElement = scope.querySelector(".schedule-table") as HTMLElement;
    const unscheduledGamesElement = scope.querySelector(".unscheduled-games") as HTMLElement;
    const scheduleTableSlotElements = scope.querySelectorAll(".schedule-table-slot") as NodeListOf<HTMLElement>;

    const options: Sortable.Options = {
        group: "schedule-shared",
        animation: 150,
        onStart: (evt) => {
            console.log("Drag started", evt);
            const availableTimeslotIds = [...evt.item.querySelectorAll("[data-available]")].map(
                (el) => (el as HTMLElement).dataset.availableTimeSlotId,
            );
            const availableTimeslotElements = scheduleTableElement.querySelectorAll(
                `[data-time-slot-id="${availableTimeslotIds.join('"], [data-time-slot-id="')}"]`,
            );
            for (const el of availableTimeslotElements) {
                el.classList.remove("bg-black");
            }
            const unavailableTimeslotElements = scheduleTableElement.querySelectorAll(
                `[data-time-slot-id]:not([data-time-slot-id="${availableTimeslotIds.join('"], [data-time-slot-id="')}"])`,
            );
            for (const el of unavailableTimeslotElements) {
                el.classList.add("bg-black");
            }
        },
        onEnd: (evt) => {
            console.log("Drag ended", evt);
            const allTimeslotElements = scheduleTableElement.querySelectorAll("[data-time-slot-id]");
            for (const el of allTimeslotElements) {
                el.classList.remove("bg-black");
            }
        },
    };

    for (const slot of scheduleTableSlotElements) {
        Sortable.create(slot, options);
    }

    Sortable.create(unscheduledGamesElement, options);
};

export default event_manage_schedule;
