variable "DOCKER_STAGE" {
    default = "default"
}

variable "DOCKER_TAG" {
    default = "dev"
}

target "default" {
    secret = [
        { type = "file", id = "npmrc", src = "./.npmrc" },
    ]
    context = "."
    dockerfile = "Dockerfile"
    target = "${DOCKER_STAGE}"
    tags = [
        "jcheatley/waikato-rpg-convergence-games:${DOCKER_TAG}",
    ]
    args = {
        BUILD_TIME = timestamp()
    }
}