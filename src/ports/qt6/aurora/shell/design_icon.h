#pragma once
#include <QFile>
#include <QImage>
#include <QPainter>

// Target Qt has no QtSvg/PNG decoder. Build-time QtSvg renders the original
// artwork into premultiplied BGRA pixels; retain alpha, never substitute glyphs.
class DesignIcon {
    QImage image;
public:
    explicit DesignIcon(const QString &path) {
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) return;
        const QByteArray bytes = file.readAll();
        constexpr int side = 192;
        if (bytes.size() != side * side * 4) return;
        image = QImage(reinterpret_cast<const uchar *>(bytes.constData()), side, side,
                       side * 4, QImage::Format_ARGB32_Premultiplied).copy();
    }
    bool isValid() const { return !image.isNull(); }
    void render(QPainter *painter, const QRectF &rect) {
        painter->save();
        painter->setRenderHint(QPainter::SmoothPixmapTransform);
        painter->drawImage(rect, image);
        painter->restore();
    }
};
