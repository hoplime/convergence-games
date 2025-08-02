import Sortable from "sortablejs";

type GameCard = HTMLElement & {
    criteria: string[] | undefined;
};

type ScheduleTableSlot = HTMLElement & {
    provides: string[] | undefined;
};

const errorBgStyle = "bg-error/25";
const errorTextStyle = "text-error";
const warningBgStyle = "bg-warning/25";

const criterionMatches = (criterion: string, provides: string[]): boolean => {
    if (criterion.includes("|")) {
        // Split the criterion by "|" and check if any of the provides match
        const subCriteria = criterion.split("|");
        return subCriteria.some((subCriterion) => criterionMatches(subCriterion, provides));
    }
    // If the criterion starts with "!", it means it should not match
    let negated = criterion.startsWith("!");
    if (negated) {
        criterion = criterion.slice(1); // Remove the "!" for matching
        return !provides.includes(criterion);
    }
    return provides.includes(criterion);
};

const unmatchedCriteria = (criteria: string[], provides: string[]) => {
    // Check for the criteria that are not met by the provides
    // And return them as a string array
    return criteria.filter((criterion) => !criterionMatches(criterion, provides));
};

const updateGameCardDisplay = (gameCard: GameCard, scheduleTableSlot: ScheduleTableSlot | HTMLElement) => {
    // If the scheduleTableSlot has undefined provides, it is the unscheduled games element - so nothing is unmatched
    const unmatched =
        !("provides" in scheduleTableSlot) || scheduleTableSlot.provides === undefined
            ? []
            : unmatchedCriteria(gameCard.criteria || [], scheduleTableSlot.provides || []);

    clearGameCardDisplay(gameCard);

    if (unmatched.length !== 0) {
        // If not all criteria are met, show the game card with a warning or error style
        // If the unmatched criteria include a time slot or gm-id, use an error style
        const isError = unmatched.some(
            (criterion) => criterion.startsWith("time-slot-") || criterion.startsWith("!gm-"),
        );
        gameCard.classList.add(isError ? errorBgStyle : warningBgStyle);

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
    gameCard.classList.remove(warningBgStyle);

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
    const summaryElements = scope.querySelectorAll(".time-slot-summary") as NodeListOf<HTMLElement>;

    const options: Sortable.Options = {
        group: "schedule-shared",
        animation: 150,
        emptyInsertThreshold: 0,
        delay: 0,
        forceFallback: true,
        forceAutoScrollFallback: true,
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
                // Take a copy of the provides array to avoid modifying the original
                const provides = slot.provides ? [...slot.provides] : [];
                if (!provides) {
                    console.warn("No provides found for schedule table slot:", slot);
                    continue;
                }

                // Edge case - moving to the same time slot and already has a single instance of the gm-id
                // We can remove this provided gm-id - as it's created by THIS game card, so it might be valid to move it there (different table, same time slot)
                const gmId = (evt.item as GameCard).dataset.gmId;
                if (provides.includes(`gm-${gmId}`) && slot.dataset.timeSlotId === evt.from.dataset.timeSlotId) {
                    // Remove the gm-id from the provides
                    const index = provides.indexOf(`gm-${gmId}`);
                    if (index !== -1) {
                        provides.splice(index, 1);
                    }
                }

                // Check if the slot provides ALL of the criteria
                // If the criteria includes a "|", split it and check if any of the provides match
                const unmatched = unmatchedCriteria(criteria, provides);

                if (unmatched.length === 0) {
                    slot.classList.add("bg-success/25");
                }

                if (
                    unmatched.length === 1 &&
                    !unmatched[0].startsWith("time-slot") &&
                    !unmatched[0].startsWith("!gm-")
                ) {
                    // If there is only one unmatched criterion (excluding the time slot, and gm, which must be valid), highlight the slot
                    slot.classList.add("bg-warning/25");
                }
            }
        },
        onEnd: (evt) => {
            console.log("Drag ended", evt);
            for (const el of scheduleTableSlotElements) {
                el.classList.remove("bg-success/25");
                el.classList.remove("bg-warning/25");
            }

            const gameCard = evt.item as GameCard;
            const gmId = gameCard.dataset.gmId as string;
            const playerCountMinimum = gameCard.dataset.playerCountMinimum
                ? parseInt(gameCard.dataset.playerCountMinimum, 10)
                : 0;
            const playerCountOptimum = gameCard.dataset.playerCountOptimum
                ? parseInt(gameCard.dataset.playerCountOptimum, 10)
                : 0;
            const playerCountMaximum = gameCard.dataset.playerCountMaximum
                ? parseInt(gameCard.dataset.playerCountMaximum, 10)
                : 0;

            const fromElement = evt.from as ScheduleTableSlot | HTMLElement;
            const fromTimeSlotId = fromElement.dataset.timeSlotId;
            const toElement = evt.to as ScheduleTableSlot | HTMLElement;
            const toTimeSlotId = toElement.dataset.timeSlotId;

            // Add the gm-id to the provides of every schedule table slot in the column (with the same time slot) as the to element
            // EXCEPT the toElement itself
            if ("provides" in toElement) {
                // Find all the schedule table slots with the same time slot id
                const matchingSlots = Array.from(scheduleTableSlotElements).filter(
                    (slot) => slot.dataset.timeSlotId === toTimeSlotId && slot !== toElement,
                ) as ScheduleTableSlot[];
                // Add the gm-id to the provides of each matching slot
                for (const slot of matchingSlots) {
                    if (!slot.provides) {
                        // If provides is undefined, initialize it
                        slot.provides = [];
                    }
                    slot.provides.push(`gm-${gmId}`);
                    // If this slot contains a GameCard, update its display - as it may now be invalid
                    const gameCardInSlot = slot.querySelector(".game-card") as GameCard | null;
                    if (gameCardInSlot) {
                        updateGameCardDisplay(gameCardInSlot, slot);
                    }
                }
            }

            // Remove the gm-id from the provides of every schedule table slot in the column (with the same time slot) as the from element
            // EXCEPT the fromElement itself
            if ("provides" in fromElement) {
                // Find all the schedule table slots with the same time slot id
                const matchingSlots = Array.from(scheduleTableSlotElements).filter(
                    (slot) => slot.dataset.timeSlotId === fromTimeSlotId && slot !== fromElement,
                ) as ScheduleTableSlot[];
                // Remove the gm-id from the provides of each matching slot
                // Just remove one instance of the gm-id
                // This is to ensure that if the gm-id was added multiple times, it only gets removed once
                for (const slot of matchingSlots) {
                    if (slot.provides) {
                        const index = slot.provides.indexOf(`gm-${gmId}`);
                        if (index !== -1) {
                            console.log("Removing gm-id from slot provides:", slot, "with gmId:", gmId);
                            slot.provides.splice(index, 1);
                            // If this slot contains a GameCard, update its display - as it may now be valid
                            const gameCardInSlot = slot.querySelector(".game-card") as GameCard | null;
                            if (gameCardInSlot) {
                                console.log("Updating game card display for slot:", slot, "because gm-id was removed");
                                updateGameCardDisplay(gameCardInSlot, slot);
                            }
                        }
                    }
                }
            }

            // Add the counts to the summary information with the same time slot id as the to element
            const toSummaryElement = Array.from(summaryElements).find(
                (el) => el.dataset.timeSlotId === toTimeSlotId,
            ) as HTMLElement | undefined;
            if (toSummaryElement) {
                // Update the summary spans within the summary element
                toSummaryElement.querySelectorAll(".summary-gm-count").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) + 1).toString();
                });
                toSummaryElement.querySelectorAll(".summary-player-minimum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) + playerCountMinimum).toString();
                });
                toSummaryElement.querySelectorAll(".summary-player-optimum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) + playerCountOptimum).toString();
                });
                toSummaryElement.querySelectorAll(".summary-player-maximum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) + playerCountMaximum).toString();
                });
                toSummaryElement.querySelectorAll(".summary-total-minimum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) + playerCountMinimum).toString();
                });
                toSummaryElement.querySelectorAll(".summary-total-optimum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) + playerCountOptimum).toString();
                });
                toSummaryElement.querySelectorAll(".summary-total-maximum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) + playerCountMaximum).toString();
                });
            }

            // Subtract the counts from the summary information with the same time slot id as the from element
            const fromSummaryElement = Array.from(summaryElements).find(
                (el) => el.dataset.timeSlotId === fromTimeSlotId,
            ) as HTMLElement | undefined;
            if (fromSummaryElement) {
                // Update the summary spans within the summary element
                fromSummaryElement.querySelectorAll(".summary-gm-count").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) - 1).toString();
                });
                fromSummaryElement.querySelectorAll(".summary-player-minimum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) - playerCountMinimum).toString();
                });
                fromSummaryElement.querySelectorAll(".summary-player-optimum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) - playerCountOptimum).toString();
                });
                fromSummaryElement.querySelectorAll(".summary-player-maximum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) - playerCountMaximum).toString();
                });
                fromSummaryElement.querySelectorAll(".summary-total-minimum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) - playerCountMinimum).toString();
                });
                fromSummaryElement.querySelectorAll(".summary-total-optimum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) - playerCountOptimum).toString();
                });
                fromSummaryElement.querySelectorAll(".summary-total-maximum").forEach((el) => {
                    el.textContent = (parseInt(el.textContent || "0", 10) - playerCountMaximum).toString();
                });
            }

            // Update the game card's display based on the target slot
            updateGameCardDisplay(gameCard, toElement);
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
