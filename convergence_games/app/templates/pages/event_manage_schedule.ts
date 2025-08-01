import Sortable from "sortablejs";

type GameCard = HTMLElement & {
    criteria: string[] | undefined;
};

type ScheduleTableSlot = HTMLElement & {
    provides: string[] | undefined;
};

const event_manage_schedule = (scope_id: string) => {
    const scope = document.getElementById(scope_id);
    if (!scope) {
        console.error(`Scope with id ${scope_id} not found`);
        return;
    }

    // const scheduleTableElement = scope.querySelector(".schedule-table") as HTMLElement;
    const unscheduledGamesElement = scope.querySelector(".unscheduled-games") as HTMLElement;
    const scheduleTableSlotElements = scope.querySelectorAll(".schedule-table-slot") as NodeListOf<ScheduleTableSlot>;
    const gameCardElements = scope.querySelectorAll(".game-card") as NodeListOf<GameCard>;

    const options: Sortable.Options = {
        group: "schedule-shared",
        animation: 150,
        onStart: (evt) => {
            // Check if the dragged item has a criteria property
            const criteria = (evt.item as GameCard).criteria;
            if (!criteria) {
                console.error("No criteria found on the dragged item");
                return;
            }
            console.log("Criteria for drag:", criteria);

            // Highlight available time slots based on the dragged item's criteria
            for (const slot of scheduleTableSlotElements) {
                const provides = slot.provides;
                if (!provides) {
                    console.warn("No provides found for schedule table slot:", slot);
                    continue;
                }
                // Check if the slot provides ALL of the criteria
                // If the criteria includes a "|", split it and check if any of the provides match
                const matches = criteria.every((criterion) => {
                    console.log("Checking criterion:", criterion, "against provides:", provides);
                    if (criterion.includes("|")) {
                        // Split the criterion by "|" and check if any of the provides match
                        const subCriteria = criterion.split("|");
                        return subCriteria.some((subCriterion) => provides.includes(subCriterion));
                    }
                    // Otherwise, check if the single criterion matches
                    return provides.includes(criterion);
                });

                if (matches) {
                    slot.classList.add("bg-success/25");
                    console.log("Slot matches criteria:", slot, "with provides:", provides);
                }
            }
        },
        onEnd: (evt) => {
            console.log("Drag ended", evt);
            for (const el of scheduleTableSlotElements) {
                el.classList.remove("bg-success/25");
            }
        },
    };

    // Initialize Sortable
    for (const slot of scheduleTableSlotElements) {
        Sortable.create(slot, options);
    }

    Sortable.create(unscheduledGamesElement, options);

    // Set the game cards criteria properties by JSON parsing the data-criteria attribute
    for (const gameCard of gameCardElements) {
        const criteriaString = gameCard.dataset.criteria;
        if (criteriaString) {
            try {
                const criteria = JSON.parse(criteriaString) as string[];
                gameCard.criteria = criteria;
            } catch (error) {
                console.error("Failed to parse criteria string:", criteriaString, error);
            }
        } else {
            console.warn("No criteria found for game card:", gameCard);
        }
    }

    // Set the schedule table slot provides properties by JSON parsing the data-provides attribute
    for (const slot of scheduleTableSlotElements) {
        const providesString = slot.dataset.provides;
        if (providesString) {
            try {
                const provides = JSON.parse(providesString) as string[];
                slot.provides = provides;
            } catch (error) {
                console.error("Failed to parse provides string:", providesString, error);
            }
        } else {
            console.warn("No provides found for schedule table slot:", slot);
        }
    }
};

export default event_manage_schedule;
