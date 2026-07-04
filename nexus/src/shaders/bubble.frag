#version 300 es
precision highp float;

in vec2 v_local_pos;
in vec4 v_color;
in float v_type;
in float v_time;

out vec4 fragColor;

void main() {
    float dist;
    float alpha;

    if (v_type < 0.5) {
        dist = length(v_local_pos);
        alpha = 1.0 - smoothstep(1.0 - fwidth(dist), 1.0, dist);
    } else if (v_type < 1.5) {
        vec2 d = abs(v_local_pos);
        dist = max(d.x, d.y);
        alpha = 1.0 - smoothstep(0.9 - fwidth(dist), 0.9, dist);
    } else if (v_type < 2.5) {
        dist = length(v_local_pos);
        alpha = 1.0 - smoothstep(1.0 - fwidth(dist), 1.0, dist);
        alpha *= 0.7;
    } else {
        dist = length(v_local_pos);
        float pulse = 0.5 + 0.5 * sin(v_time * 6.2831853);
        alpha = 1.0 - smoothstep(1.0 - fwidth(dist), 1.0, dist);
        alpha *= (0.5 + 0.5 * pulse);
        fragColor = vec4(v_color.rgb, alpha * v_color.a);
        return;
    }

    fragColor = vec4(v_color.rgb, alpha * v_color.a);
}
