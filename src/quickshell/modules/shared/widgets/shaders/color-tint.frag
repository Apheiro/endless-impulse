#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec4 tintColor;
} ubuf;
layout(binding = 1) uniform sampler2D source;

float luminance(vec3 color) {
    return dot(color, vec3(0.30, 0.59, 0.11));
}

// Non-separable Color blend: SetLum(tint, Lum(original)), with gamut clipping.
// Clip around the same luminance rather than flattening shadows or highlights.
vec3 setLuminance(vec3 color, float light) {
    color += light - luminance(color);
    float low = min(color.r, min(color.g, color.b));
    float high = max(color.r, max(color.g, color.b));
    if (low < 0.0)
        color = vec3(light) + (color - vec3(light)) * light / max(light - low, 0.00001);
    if (high > 1.0)
        color = vec3(light) + (color - vec3(light)) * (1.0 - light) / max(high - light, 0.00001);
    return color;
}

void main() {
    vec4 pixel = texture(source, qt_TexCoord0);
    vec3 original = pixel.a > 0.0 ? pixel.rgb / pixel.a : vec3(0.0);
    vec3 tint = ubuf.tintColor.a > 0.0 ? ubuf.tintColor.rgb / ubuf.tintColor.a : original;
    vec3 colored = setLuminance(tint, luminance(original));
    // Both texture samples and QML colors are premultiplied. Keep the source alpha.
    fragColor = vec4(mix(original, colored, ubuf.tintColor.a) * pixel.a, pixel.a) * ubuf.qt_Opacity;
}
