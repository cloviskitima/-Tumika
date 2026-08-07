from pathlib import Path
path = Path('templates/ventes.html')
text = path.read_text(encoding='utf-8')
old = '''    container.innerHTML = products.map(product => {
        const status = getStockStatus(product.quantite, product.stock_min);
        const imageUrl = product.image_url_1 || product.image_url_2 || '';
        return '<div style="padding: 12px; border-bottom: 1px solid var(--gray-200); display: flex; gap: 12px; align-items: center; cursor: pointer;" onclick="addToCart(' + product.id + ')">' +
            '<div style="width: 64px; height: 64px; border-radius: 12px; overflow: hidden; background: #f5f7fb; display: flex; align-items: center; justify-content: center;>\n                ' + (imageUrl ? '<img src="' + imageUrl + '" alt="' + product.nom + '" style="width: 100%; height: 100%; object-fit: cover;">' : '<i class="bi bi-box-seam" style="font-size: 1.5rem; color: #6b7280;"></i>') + '\n            </div>' +
            '<div style="flex: 1;>\n                <div style="font-weight: 500;">' + product.nom + '</div>' +
                '<div style="font-size: 0.85rem; color: var(--gray-500);">Réf: ' + product.reference + ' • Stock: ' + product.quantite + ' • ' + formatCurrency(product.prix_vente) + '</div>' +
                '<div style="font-size: 0.85rem; margin-top: 4px;">Statut: ' + status + '</div>' +
            '</div>' +
            '<button class="btn btn-primary" style="padding: 4px 8px; font-size: 0.85rem;"><i class="bi bi-plus"></i></button>' +
        '</div>';
    }).join('');
'''
new = '''    container.innerHTML = products.map(product => {
        const status = getStockStatus(product.quantite, product.stock_min);
        const imageUrl = product.image_url_1 || product.image_url_2 || '';
        return (
            '<div style="padding: 12px; border-bottom: 1px solid var(--gray-200); display: flex; gap: 12px; align-items: center; cursor: pointer;" onclick="addToCart(' + product.id + ')">' +
                '<div style="width: 64px; height: 64px; border-radius: 12px; overflow: hidden; background: #f5f7fb; display: flex; align-items: center; justify-content: center;">' +
                    (imageUrl ? '<img src="' + imageUrl + '" alt="' + product.nom + '" style="width: 100%; height: 100%; object-fit: cover;">' : '<i class="bi bi-box-seam" style="font-size: 1.5rem; color: #6b7280;"></i>') +
                '</div>' +
                '<div style="flex: 1;">' +
                    '<div style="font-weight: 500;">' + product.nom + '</div>' +
                    '<div style="font-size: 0.85rem; color: var(--gray-500);">Réf: ' + product.reference + ' • Stock: ' + product.quantite + ' • ' + formatCurrency(product.prix_vente) + '</div>' +
                    '<div style="font-size: 0.85rem; margin-top: 4px;">Statut: ' + status + '</div>' +
                '</div>' +
                '<button class="btn btn-primary" style="padding: 4px 8px; font-size: 0.85rem;"><i class="bi bi-plus"></i></button>' +
            '</div>'
        );
    }).join('');
'''
if old not in text:
    raise ValueError('Old block not found')
path.write_text(text.replace(old, new), encoding='utf-8')
print('patched')
