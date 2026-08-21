const scroll_button = (element_id: string) => {
    document.addEventListener('DOMContentLoaded', (_: Event) => {
        const button = document.getElementById(element_id);
        if (!button) {
            console.error(`Could not find ${element_id} element`);
            return;
        }

        button.addEventListener('click', () => {
            document.documentElement.scrollTo({
                top: 0,
                behavior: "smooth",
            });
        });
    });
}

export default scroll_button;