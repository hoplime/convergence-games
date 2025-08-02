import Sortable from "sortablejs";

type GameCard = HTMLElement & {
    criteria: string[] | undefined;
};

type ScheduleTableSlot = HTMLElement & {
    provides: string[] | undefined;
};

const errorBgStyle = "bg-error/25";
const errorTextStyle = "text-error";

const unmatchedCriteria = (criteria: string[], provides: string[]) => {
    // Check for the criteria that are not met by the provides
    // And return them as a string array
    return criteria.filter((criterion) => {
        if (criterion.includes("|")) {
            // Split the criterion by "|" and check if any of the provides match
            const subCriteria = criterion.split("|");
            return !subCriteria.some((subCriterion) => provides.includes(subCriterion));
        }
        // Otherwise, check if the single criterion matches
        return !provides.includes(criterion);
    });
};

const updateGameCardDisplay = (gameCard: GameCard, scheduleTableSlot: ScheduleTableSlot) => {
    // Update the game card's display based on where it was dropped
    const provides = scheduleTableSlot.provides || [];
    // If we have no provides, then this is not a scheduleTableSlot
    const unmatched =
        provides.length === 0 ? [] : unmatchedCriteria(gameCard.criteria || [], scheduleTableSlot.provides || []);

    clearGameCardDisplay(gameCard);

    if (unmatched.length !== 0) {
        // If not all criteria are met, show the game card with a warning style
        gameCard.classList.add(errorBgStyle);

        // And find the elements with unmatched data-criteria attributes
        Array.from(gameCard.querySelectorAll("[data-criteria-match]"))
            .filter((el) => {
                const criterion = el.getAttribute("data-criteria-match");
                return criterion && unmatched.includes(criterion);
            })
            .forEach((el) => {
                el.classList.add(errorTextStyle);
            });
    }
};

const clearGameCardDisplay = (gameCard: GameCard) => {
    // Clear the game card's display styles
    gameCard.classList.remove(errorBgStyle);

    // Clear each element's criteria warnings
    Array.from(gameCard.querySelectorAll("[data-criteria-match]")).forEach((el) => {
        el.classList.remove(errorTextStyle);
    });
};

const event_manage_schedule = (scope_id: string) => {
    const scope = document.getElementById(scope_id);
    if (!scope) {
        console.error(`Scope with id ${scope_id} not found`);
        return;
    }

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
                const unmatched = unmatchedCriteria(criteria, provides);
                const matches = unmatched.length === 0;

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

            // Update the game card's display based on where it was dropped
            const targetElement = evt.to;
            if (targetElement == unscheduledGamesElement) {
                // If dropped back to unscheduled games, clear the display
                clearGameCardDisplay(evt.item as GameCard);
                return;
            }
            // Update the game card's display based on the target slot
            const targetSlot = targetElement as ScheduleTableSlot;
            updateGameCardDisplay(evt.item as GameCard, targetSlot);
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
