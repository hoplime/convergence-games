variable "DOCKER_STAGE" {
    default = "default"
}

target "default" {
    secret = [
        { type = "file", id = "npmrc", src = "./.npmrc" },
    ]
    context = "."
    dockerfile = "Dockerfile"
    target = "${DOCKER_STAGE}"
    tags = [
        "jcheatley/waikato-rpg-convergence-games:latest"
    ]
    args = {
        BUILD_TIME = timestamp()
    }
}