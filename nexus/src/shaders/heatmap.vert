#version 300 es
precision highp float;

layout(location = 0) in vec2 a_position;

uniform mat4 u_MVP;
uniform float u_scroll_offset;
uniform vec2 u_resolution;

out vec2 v_texcoord;

void main() {
    v_texcoord = a_position;
    v_texcoord.x = fract(v_texcoord.x + u_scroll_offset);

    gl_Position = u_MVP * vec4(a_position, 0.0, 1.0);
}
