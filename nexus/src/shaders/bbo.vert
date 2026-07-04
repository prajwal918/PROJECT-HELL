#version 300 es
precision highp float;

layout(location = 0) in vec2 a_position;
layout(location = 1) in float a_side_flag;

uniform mat4 u_MVP;

out vec4 v_color;

void main() {
    if (a_side_flag < 0.5) {
        v_color = vec4(0.0, 1.0, 0.533, 1.0);
    } else {
        v_color = vec4(1.0, 0.267, 0.4, 1.0);
    }

    gl_Position = u_MVP * vec4(a_position, 0.0, 1.0);
}
