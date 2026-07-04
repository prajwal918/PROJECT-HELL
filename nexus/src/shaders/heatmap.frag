#version 300 es
precision highp float;

uniform sampler2D u_heatmap_texture;
uniform sampler2D u_lut_texture;
uniform float u_contrast_scale;

in vec2 v_texcoord;

out vec4 fragColor;

void main() {
    float raw_intensity = texture(u_heatmap_texture, v_texcoord).r;
    float normalized = clamp(raw_intensity * u_contrast_scale, 0.0, 1.0);
    vec4 color = texture(u_lut_texture, vec2(normalized, 0.5));
    fragColor = color;
}
