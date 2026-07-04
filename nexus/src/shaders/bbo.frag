#version 300 es
precision highp float;

in vec4 v_color;

out vec4 fragColor;

void main() {
    vec2 pixel_coord = gl_FragCoord.xy;
    float dy = fwidth(pixel_coord.y);
    float line_width = 1.0;

    fragColor = v_color;
}
