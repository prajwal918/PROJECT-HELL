#version 300 es
precision highp float;

layout(location = 0) in vec2 a_position;
layout(location = 1) in vec2 a_inst_position;
layout(location = 2) in float a_inst_radius;
layout(location = 3) in vec4 a_inst_color;
layout(location = 4) in float a_inst_type;

uniform mat4 u_MVP;
uniform float u_time;
uniform vec2 u_resolution;

out vec2 v_local_pos;
out vec4 v_color;
out float v_type;
out float v_time;

void main() {
    v_local_pos = a_position;
    v_color = a_inst_color;
    v_type = a_inst_type;
    v_time = u_time;

    vec2 world_pos = a_inst_position + a_position * a_inst_radius;

    gl_Position = u_MVP * vec4(world_pos, 0.0, 1.0);
    gl_PointSize = a_inst_radius * 2.0 * (u_resolution.y / (u_MVP[1][1] * 2.0));
}
